"""Durable AVWAP shadow worker. No model, notification or order client."""
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from .candidate_packages import canonical, digest
from .comparison_live import EventClient, envelope, event_id
from .method_scenarios import PROTOCOL, PROTOCOL_ID, scenario
from .paper_comparison import _plan, aware, metrics
from .paper_outcomes import Quote, replay_long

KINDS = {'method_enrol','method_report','quote'}


class MethodShadow:
    """Disposable event projection. First durable enrolment wins per symbol/day.

    Event sequence, protocol, checksums and source inputs are verified on restore.
    Re-running a capture cannot reset expiry, rescue a miss or retry a loss.
    """
    def __init__(self, directory, *, client, observer=None, clock=lambda:datetime.now(UTC), day=None):
        self.root=Path(directory); self.root.mkdir(parents=True,exist_ok=True)
        self.journal=self.root/'method-events.jsonl'
        if self.journal.exists(): raise ValueError('fresh_method_projection_required')
        self.client,self.observer,self.clock=client,observer,clock
        self.day=day or aware(clock()).date().isoformat()
        self.experiment=PROTOCOL_ID; self.cursor=0; self.seen=set()
        self.cohorts={}; self.quotes={}; self.screen=None
        self.health={'polls':0,'quotes_received':0,'error_polls':0,'maximum_poll_gap_seconds':0,
                     'capacity_deferred':0,'target_interval_seconds':5,'model_calls':0}
        self.last_poll=None

    def apply(self, event):
        if event['event_id'] in self.seen: return
        if (event['experiment_id']!=self.experiment or event['day']!=self.day
                or event['kind'] not in KINDS or event_id(self.experiment,event)!=event['event_id']):
            raise ValueError('invalid_method_event')
        p=json.loads(event['payload_json']); now=aware(event['occurred_at'])
        if p['dataset_kind']!='forward' or p['trade_authorized'] is not False:
            raise ValueError('forward_method_only')
        if event['kind']=='method_enrol':
            s=scenario(p['inputs'],now=now)
            if s!=p['scenario'] or s['blockers'] or s['plan'] is None or p['setup_id']!=s['setup_id']:
                raise ValueError('method_scenario_not_reproducible')
            # Database receipt is also an admission boundary, never retroactive.
            start=max(now,aware(event.get('received_at',now)))
            self.cohorts.setdefault(s['setup_id'],{**s,'enrolled_at':start.isoformat()})
        elif event['kind']=='quote':
            q=Quote.model_validate(p['quote']); received=aware(p['received_at'])
            if (not re.fullmatch(r'stocks:[A-Z0-9.-]{1,30}',p['candidate_id'])
                    or not re.fullmatch(r'alpaca_iex:[a-f0-9]{64}',p['source'])
                    or q.bid>q.ask or received!=now or not 0 <= (received-q.observed_at).total_seconds() <= 60):
                raise ValueError('invalid_method_observation')
            key=(p['candidate_id'],received)
            # Overlapping workers may have the same receipt instant. Keep first,
            # deterministically in database sequence order, rather than invent order.
            self.quotes.setdefault(key,p)
        elif p['protocol_id']!=self.experiment or p['schema_version']!='method-shadow-report-v1':
            raise ValueError('invalid_method_report')
        with self.journal.open('a') as out: out.write(canonical(event)+'\n')
        self.seen.add(event['event_id'])

    def sync(self):
        for _ in range(2000):
            page=self.client.read(self.experiment,self.day,self.cursor)
            if not page['events']: return
            for e in page['events']:
                if type(e['seq']) is not int or e['seq']<=self.cursor: raise ValueError('method_event_order')
                self.apply(e); self.cursor=e['seq']
            if page['next']!=self.cursor: raise ValueError('method_cursor_mismatch')
        raise ValueError('method_sync_capacity')

    def enrol(self, inputs, *, now):
        return self.enrol_many([inputs],now=now)[0]['blockers']

    def enrol_many(self, inputs, *, now):
        self.sync()
        now=max(aware(now),aware(self.clock()))
        # One durable batch avoids spending a short entry window on up to forty
        # serial network writes. All rules are evaluated at the same frozen clock.
        active=sum(r['state'] in ('watching','open_simulation') for r in self.outcomes(now))
        known=set(self.cohorts); rows=[]; events=[]; size=0
        for source in inputs:
            try:
                s=scenario(source,now=now); blockers=s['blockers']
                if s['setup_id'] in known: blockers=['already_enrolled_this_session']
                elif not blockers and active>=40: blockers=['observer_capacity_deferred']
                if not blockers:
                    event=envelope('method_enrol',{'setup_id':s['setup_id'],'protocol_id':self.experiment,
                        'shadow_only':True,'scenario':s,'inputs':source},now)
                    length=len(canonical(event).encode())
                    if length>175000 or size+length>1_500_000: blockers=['storage_batch_capacity_deferred']
                    else:
                        events.append(event);size+=length;active+=1;known.add(s['setup_id'])
            except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError):
                blockers=['method_source_unavailable_or_invalid']
            rows.append({'candidate_id':'stocks:'+source['symbol'],'blockers':blockers})
        self.client.append(self.experiment,events)
        self.sync()
        for event in events:
            proposed=json.loads(event['payload_json'])['scenario']
            saved=self.cohorts[proposed['setup_id']]
            if {k:v for k,v in saved.items() if k!='enrolled_at'}!=proposed:
                for row in rows:
                    if row['candidate_id']==proposed['candidate_id'] and not row['blockers']:
                        row['blockers']=['concurrent_session_enrolment_preserved']
        return rows

    def outcomes(self, now):
        now=aware(now); rows=[]
        for key,s in sorted(self.cohorts.items()):
            start=aware(s['enrolled_at']); plan=s['plan']
            if start>now: continue
            qs=[Quote(observed_at=at,bid=p['quote']['bid'],ask=p['quote']['ask'])
                for (candidate,at),p in sorted(self.quotes.items(),key=lambda x:x[0][1])
                if candidate==s['candidate_id'] and start<=aware(p['quote']['observed_at'])
                and start<=at<=now]
            if start>=aware(plan['expires_at']):
                value={'status':'not_filled','reason':'durable_enrolment_after_expiry','net_pnl_eur':None}
            else:
                value=replay_long(_plan(plan),qs,decision_at=start,
                    entry_expires_at=aware(plan['expires_at']),entry_mode='breakout',exit_window_seconds=30,
                    maximum_entry_spread_bps=Decimal(20),maximum_entry_gap_bps=Decimal(20)).model_dump(mode='json')
            state=value['status']
            if state=='not_filled' and value['reason']=='no_observed_eligible_fill' and now<aware(plan['expires_at']): state='watching'
            if state=='unresolved' and now<aware(plan['exit_by']): state='open_simulation'
            rows.append({'setup_id':key,'candidate_id':s['candidate_id'],'state':state,
                'outcome':value,'observations_available':len(qs),'enrolled_at':s['enrolled_at']})
        return rows

    def poll(self):
        self.sync(); now=self.clock()
        if self.last_poll is not None:
            self.health['maximum_poll_gap_seconds']=max(self.health['maximum_poll_gap_seconds'],(now-self.last_poll).total_seconds())
        self.last_poll=now
        rows=[r for r in self.outcomes(now) if r['state'] in ('watching','open_simulation')]
        rows.sort(key=lambda r:(r['state']!='open_simulation',r['enrolled_at'],r['setup_id']))
        self.health['capacity_deferred']+=max(0,len(rows)-40)
        decisions=[{'candidate_id':r['candidate_id'],'packet_id':r['setup_id'],
            'evaluated_at':r['enrolled_at'],'plan':self.cohorts[r['setup_id']]['plan']} for r in rows[:40]]
        observed,failures=self.observer.fetch(decisions) if decisions else ([],[])
        received=self.clock(); mapping={r['packet_id']:r['candidate_id'] for r in decisions}; events=[]
        for o in observed:
            q=Quote.model_validate(o['quote'])
            if not 0 <= (received-q.observed_at).total_seconds() <= 60:
                failures.append('stale_method_quote'); continue
            events.append(envelope('quote',{'candidate_id':mapping[o['packet_id']],
                'quote':q.model_dump(mode='json'),'source':o['source'],'received_at':received.isoformat()},received))
        self.client.append(self.experiment,events); self.sync()
        self.health['polls']+=1; self.health['quotes_received']+=len(events)
        self.health['error_polls']+=bool(failures)

    def report(self):
        now=self.clock(); rows=self.outcomes(now)
        return {'schema_version':'method-shadow-report-v1','protocol_id':self.experiment,
            'protocol':PROTOCOL,'strategy_id':PROTOCOL['rules']['strategy_id'],
            'as_of':aware(now).isoformat(),'evaluation_day':self.day,'dataset_kind':'forward',
            'shadow_only':True,'trade_authorized':False,'model_calls':0,'ai_cost_eur':'0',
            'cohort_count':len(rows),'results':metrics(rows),'screen':self.screen,
            'observation_health':self.health,
            'note':'Our fixed intraday adaptation of published AVWAP/multiple-timeframe concepts. '
                'IEX HLC3 bar approximation, partial venue and captured stocks only; not trader calls or executable fills. '
                'Independent EUR500 allocations, not a portfolio return. Fixed 40bps costs; no assessed headline meaning, '
                'account permission, instrument halt or corporate-action verification. Unresolved outcomes are not profits.'}

    def close(self):
        self.sync(); report=self.report()
        (self.root/'method-report.json').write_text(json.dumps(report,indent=2)+'\n')
        self.client.append(self.experiment,[envelope('method_report',report,self.clock())]); self.sync()
        return report


def screen_capture(worker, capture, feed, *, env, clock):
    from .chart_news import checked_source
    from ..market_data.providers.alpaca_batch import fetch_histories
    from ..market_data.stock_checks import collect
    symbols=list(dict.fromkeys(r['requested_symbol'] for r in capture['captures'] if r['market']=='stocks'))
    if len(symbols)>40: raise ValueError('method_capture_capacity')
    contexts={r['payload']['symbol']:r for r in capture.get('stock_context',[])}
    # Independent full-session history: never re-anchor at a truncated 60-bar capture.
    histories=fetch_histories(symbols,env=env,clock=clock) if symbols else {}
    refs=collect(symbols,env=env,clock=clock) if symbols else None
    rows=[]; inputs_batch=[]
    for symbol in symbols:
        try:
            c=contexts[symbol]; p=c['payload']; bars=histories[symbol]
            if digest(p)!=c['payload_sha256'] or bars.status!='ok': raise ValueError('source_unavailable')
            # Freeze the validated one-symbol source subset to keep each event bounded.
            checks=dict(refs['payload']); checks['symbols']=[symbol]
            checks['catalogue_candidates']={symbol:checks['catalogue_candidates'].get(symbol,[])}
            checks['quotes']={'currency':'USD','quotes':{symbol:checks.get('quotes',{}).get('quotes',{}).get(symbol,{})}}
            inputs={'symbol':symbol,'candles':[r.model_dump(mode='json') for r in bars.candles],
                'bars_received_at':bars.retrieved_at.isoformat(),'daily':p['daily']['bars'],'context':p,
                'news_check':checked_source(feed,symbol=symbol,now=clock()),
                'reference_checks':{'payload':checks,'payload_sha256':digest(checks)}}
            inputs_batch.append(inputs)
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError):
            rows.append({'candidate_id':'stocks:'+symbol,'blockers':['method_source_unavailable_or_invalid']})
    rows.extend(worker.enrol_many(inputs_batch,now=clock()))
    worker.screen={'evaluated_at':aware(clock()).isoformat(),'examined':len(rows),
        'enrolled':sum(not r['blockers'] for r in rows),
        'blocked':sum(bool(r['blockers']) for r in rows),
        'reasons':dict(Counter(b for r in rows for b in r['blockers'])),'rows':rows}


def main():
    import argparse,os
    from .paper_observer import ReferenceObserver
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--capture',type=Path)
    p.add_argument('--evidence',type=Path); p.add_argument('--duration',type=int,default=330)
    p.add_argument('--storage-only',action='store_true'); p.add_argument('--observe-only',action='store_true'); p.add_argument('--day')
    args=p.parse_args()
    if not 0<=args.duration<=600: p.error('duration must be between 0 and 600')
    clock=lambda:datetime.now(UTC)
    worker=MethodShadow(args.output,client=EventClient(os.environ.get('REVIEW_INGEST_SECRET')),
                        observer=ReferenceObserver(os.environ),clock=clock,day=args.day)
    worker.sync()
    if not args.storage_only:
        if not args.observe_only:
            if not args.capture or not args.evidence: p.error('capture and evidence required')
            screen_capture(worker,json.loads(args.capture.read_text()),json.loads(args.evidence.read_text()),env=os.environ,clock=clock)
        else:
            worker.health['screen_unavailable']=True
        end=time.monotonic()+args.duration
        while True:
            try: worker.poll()
            except (RuntimeError,ValueError,KeyError,TypeError): worker.health['error_polls']+=1
            if time.monotonic()>=end: break
            time.sleep(min(5,max(0,end-time.monotonic())))
    report=worker.close()
    print(json.dumps({'state':'method_shadow_recorded','cohort_count':report['cohort_count'],
                      'model_calls':0,'trade_authorized':False}))


if __name__=='__main__': main()
