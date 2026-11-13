"""Independent durable experiment worker. No AI, Telegram or broker orders."""
import argparse
from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo

import requests
from .candidate_packages import canonical, digest
from .comparison_live import EventClient, envelope, event_id
from .paper_comparison import aware
from .paper_outcomes import Quote
from .strategy_experiment import PROTOCOL, PROTOCOL_ID, VARIANTS, build, replay, summarize, num, text, D, NY


def common():
    return {'protocol_id':PROTOCOL_ID,'shadow_only':True,'model_calls':0,
            'trade_authorized':False,'dataset_kind':'forward'}


class StrategyExperiment:
    def __init__(self, root, *, client, clock=lambda:datetime.now(UTC), day=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.journal=self.root/'events.jsonl'
        if self.journal.exists():raise ValueError('fresh_strategy_projection_required')
        self.client,self.clock=client,clock;self.day=day or clock().date().isoformat()
        self.cursor=0;self.seen=set();self.cohorts={};self.quotes=[];self.screen=None;self.source=[]
        self.health={'polls':0,'quotes_received':0,'error_polls':0,'maximum_poll_gap_seconds':0,
                     'capacity_deferred':0,'model_calls':0}
        self.last_poll=None

    def apply(self,event):
        if event['event_id'] in self.seen:return
        if (event['experiment_id']!=PROTOCOL_ID or event['day']!=self.day
            or event_id(PROTOCOL_ID,event)!=event['event_id']):raise ValueError('strategy_event_identity')
        p=json.loads(event['payload_json']);at=aware(event['occurred_at'])
        if p.get('dataset_kind')!='forward' or p.get('trade_authorized') is not False:raise ValueError('strategy_event_scope')
        kind=event['kind']
        if kind=='strategy_enrol':
            s=build(p['inputs'],now=at)
            if s!=p['cohort'] or s['blockers'] or s['setup_id']!=p['setup_id']:raise ValueError('strategy_cohort_replay_mismatch')
            self.cohorts.setdefault(s['setup_id'],{**s,'enrolled_at':max(at,aware(event['received_at'])).isoformat()})
        elif kind=='quote':
            q=Quote.model_validate(p['quote']);received=aware(p['received_at'])
            if (not re.fullmatch(r'stocks:[A-Z0-9.-]{1,30}',p['candidate_id'])
                or not re.fullmatch(r'alpaca_iex:[a-f0-9]{64}',p['source'])
                or received!=at or not 0<=(received-q.observed_at).total_seconds()<=60
                or q.bid>q.ask):raise ValueError('strategy_quote_invalid')
            native=p['native_quote_usd'];fx=num(p['eur_per_usd'])
            matching=[c for c in self.cohorts.values() if c['candidate_id']==p['candidate_id']]
            if not matching or fx!=num(next(iter(matching[0]['variants'].values()))['plan']['fx_rate']):raise ValueError('strategy_quote_fx_mismatch')
            if q.bid!=num(native['bid'])*fx or q.ask!=num(native['ask'])*fx:raise ValueError('strategy_quote_currency_mismatch')
            self.quotes.append({**p,'durable_received_at':event['received_at']})
        elif kind=='strategy_screen':
            if p['schema_version']!='strategy-experiment-screen-v1' or p['protocol_id']!=PROTOCOL_ID:raise ValueError('strategy_screen_identity')
            self.screen=p
        elif kind=='strategy_report':
            if p['schema_version']!='strategy-experiment-report-v1' or p['protocol_id']!=PROTOCOL_ID:raise ValueError('strategy_report_identity')
        else:raise ValueError('strategy_event_kind')
        self.seen.add(event['event_id'])
        if kind!='strategy_report':self.source.append(event)
        with self.journal.open('a') as f:f.write(canonical(event)+'\n')

    def sync(self):
        start=time.monotonic()
        for _ in range(250):
            page=self.client.read(PROTOCOL_ID,self.day,self.cursor)
            if not page['events']:break
            for event in page['events']:
                if type(event['seq']) is not int or event['seq']<=self.cursor:raise ValueError('strategy_event_order')
                self.apply(event);self.cursor=event['seq']
            if page['next']!=self.cursor:raise ValueError('strategy_cursor_mismatch')
            if len(self.source)>100000 or self.journal.stat().st_size>75_000_000 or time.monotonic()-start>90:
                raise ValueError('strategy_restore_capacity')
        else:raise ValueError('strategy_page_capacity')

    def outcomes(self,now):
        by_symbol={}
        for q in self.quotes:by_symbol.setdefault(q['candidate_id'],[]).append(q)
        return {key:replay(c,by_symbol.get(c['candidate_id'],[]),now=now) for key,c in self.cohorts.items()}

    def active(self,now):
        return [self.cohorts[key] for key,variants in self.outcomes(now).items()
                if any(r['state'] in ('watching','open') for r in variants.values())]

    def enrol(self,inputs,*,capture_sha,source_failures=()):
        self.sync();now=self.clock();active=len(self.active(now));events=[];rows=list(source_failures);known=set(self.cohorts)
        from .strategy_diagnostics import input_trace
        self.screen_trace=[]
        for source in inputs:
            s=build(source,now=now);blocks=s['blockers'][:]
            if not blocks and s['setup_id'] in known:blocks=['already_frozen_this_session']
            if not blocks and active>=40:blocks=['observer_capacity_deferred'];self.health['capacity_deferred']+=1
            if not blocks:
                p={**common(),'schema_version':'strategy-experiment-enrol-v1','setup_id':s['setup_id'],'inputs':source,'cohort':s}
                e=envelope('strategy_enrol',p,now)
                if len(e['payload_json'].encode())>175000:blocks=['source_event_capacity']
                else:
                    events.append(e);known.add(s['setup_id'])
                    active+=any(not v['blockers'] for v in s['variants'].values())
            rows.append({'candidate_id':'stocks:'+source['symbol'],'blockers':blocks})
            self.screen_trace.append({**input_trace(source,now),'blockers':blocks})
        # Bounded writes; one failed/ambiguous batch stops enrolment. Restore
        # authoritative events rather than repeating an uncertain append.
        batch=[];size=0
        for e in events:
            n=len(canonical(e).encode())
            if size+n>1_500_000 or len(batch)>=30:self.client.append(PROTOCOL_ID,batch);batch=[];size=0
            batch.append(e);size+=n
        self.client.append(PROTOCOL_ID,batch);self.sync()
        stamp=self.clock()
        self.screen={**common(),'schema_version':'strategy-experiment-screen-v1','as_of':stamp.isoformat(),
                     'evaluation_day':self.day,'capture_sha256':capture_sha,'examined':len(rows),
                     'enrolled':len(events),'reasons':dict(Counter(b for r in rows for b in r['blockers'])),'rows':rows}
        self.client.append(PROTOCOL_ID,[envelope('strategy_screen',self.screen,stamp)]);self.sync()

    def poll(self,observer):
        self.sync();now=self.clock()
        if self.last_poll:self.health['maximum_poll_gap_seconds']=max(self.health['maximum_poll_gap_seconds'],(now-self.last_poll).total_seconds())
        self.last_poll=now;active=self.active(now)
        active.sort(key=lambda c:(c['enrolled_at'],c['setup_id']))
        self.health['capacity_deferred']+=max(0,len(active)-40)
        observations,failures=observer.fetch(active[:40]) if active else ([],[])
        events=[envelope('quote',o,aware(o['received_at'])) for o in observations]
        self.client.append(PROTOCOL_ID,events);self.sync()
        self.health['polls']+=1;self.health['quotes_received']+=len(events);self.health['error_polls']+=bool(failures)
        self.health['last_active_symbols']=len(active)
        if failures:self.health['last_errors']=sorted(set(failures))[:10]
        self.health['last_success_at']=self.clock().isoformat()

    def report(self):
        now=self.clock();outcomes=self.outcomes(now);rows=[];variant_rows={k:[] for k in VARIANTS}
        for key,variants in sorted(outcomes.items()):
            for name,r in variants.items():
                variant_rows[name].append(r)
                rows.append({'setup_id':key,'candidate_id':self.cohorts[key]['candidate_id'],'variant':name,**r,
                             'plan':self.cohorts[key]['variants'][name]['plan']})
        result={**common(),'schema_version':'strategy-experiment-report-v1','as_of':now.isoformat(),
                'evaluation_day':self.day,'cohort_count':len(outcomes),
                'variants':{name:summarize(items) for name,items in variant_rows.items()},
                'screen':self.screen,'observation_health':self.health,'rows':rows[:100],'rows_omitted':max(0,len(rows)-100),
                'source_event_count':len(self.source),'source_events_sha256':digest(self.source),
                'note':'Unproven matched continuation experiment, not the exact production AI strategy. First common eligible setup per symbol/day, all variants frozen together. '
                       'IEX reference quotes, assumed slippage and conditional fees; independent allocations, not a portfolio or broker fills. '
                       'No AI calls or orders. Missing/open/unresolved observations are not zero profit. Day/regime evidence is needed; '
                       '12 November is commissioning, full-session prospective validation starts 13 November. No parameter tuning during validation.'}
        while len(canonical(result).encode())>175000 and result['rows']:
            result['rows'].pop();result['rows_omitted']+=1
        if len(canonical(result).encode())>175000:raise ValueError('strategy_report_capacity')
        return result

    def close(self):
        self.sync();r=self.report()
        (self.root/'report.json').write_text(canonical(r)+'\n')
        (self.root/'paired-results.json').write_text(canonical(paired_results(self,aware(r['as_of'])))+'\n')
        self.client.append(PROTOCOL_ID,[envelope('strategy_report',r,aware(r['as_of']))])
        from .strategy_diagnostics import build as diagnose, bounded, PROTOCOL_ID as DIAGNOSTICS_PROTOCOL
        evidence=diagnose(self,aware(r['as_of']))
        (self.root/'strategy-diagnostics.json').write_text(canonical(evidence)+'\n')
        self.client.append(DIAGNOSTICS_PROTOCOL,[envelope('audit',bounded(evidence),self.clock())])
        return r


class StrategyObserver:
    """Native USD quotes converted using each frozen cohort's FX rate."""
    def __init__(self,env,*,clock=lambda:datetime.now(UTC),session=None):
        self.env,self.clock,self.session=env,clock,session or requests.Session()
    def fetch(self,cohorts):
        from ..market_data.stock_checks import get,QUOTES,CLOCK
        symbols=[c['symbol'] for c in cohorts];failures=[];out=[]
        if len(symbols)>40 or len(set(symbols))!=len(symbols):raise ValueError('strategy_observer_capacity')
        try:
            market=get(CLOCK,{},self.env,self.session)
            if market['is_open'] is not True or not 0<=(self.clock()-aware(market['timestamp'])).total_seconds()<60:
                return [],['market_clock_unavailable_or_closed']
            raw=get(QUOTES,{'symbols':','.join(symbols),'feed':'iex','currency':'USD'},self.env,self.session)
        except (requests.RequestException,KeyError,ValueError,TypeError):return [],['quote_batch_unavailable']
        for c in cohorts:
            try:
                q=raw['quotes'][c['symbol']];at=aware(q['t']);received=self.clock();bid,ask=num(q['bp']),num(q['ap'])
                if not 0<bid<=ask or min(num(q['bs']),num(q['as']))<=0 or not 0<=(received-at).total_seconds()<=30:
                    raise ValueError('quote_unavailable')
                fx=num(next(iter(c['variants'].values()))['plan']['fx_rate'])
                out.append({**common(),'candidate_id':c['candidate_id'],'quote':{'observed_at':at.isoformat(),'bid':text(bid*fx),'ask':text(ask*fx)},
                            'native_quote_usd':{'bid':text(bid),'ask':text(ask)},'eur_per_usd':text(fx),
                            'source':'alpaca_iex:'+digest(q),'received_at':received.isoformat()})
            except (KeyError,TypeError,ValueError,ArithmeticError):failures.append('quote_unavailable:'+c['symbol'])
        return out,failures


def paired_results(worker,now):
    """Pair only observed closed outcomes; all other states remain excluded/unknown."""
    outcomes=worker.outcomes(now);pairs={}
    definitions={
        'volume_with_structural_usd':('rolling_structural_usd','same_time_structural_usd'),
        'volume_with_atr_usd':('rolling_atr_usd','same_time_atr_usd'),
        'risk_with_rolling_usd':('rolling_structural_usd','rolling_atr_usd'),
        'risk_with_same_time_usd':('same_time_structural_usd','same_time_atr_usd'),
        'cost_with_same_time_atr':('same_time_atr_flat40','same_time_atr_usd'),
        'eur_conversion_sensitivity':('same_time_atr_usd','same_time_atr_eur'),
        'stress_sensitivity':('same_time_atr_usd','same_time_atr_stress'),
    }
    for label,(control,changed) in definitions.items():
        matched=[(key,rows) for key,rows in outcomes.items() if rows[control]['state']==rows[changed]['state']=='closed']
        pairs[label]={'control':control,'changed':changed,'matched_closed':len(matched),'excluded':len(outcomes)-len(matched),
                      'changed_minus_control_net_eur':text(sum((num(rows[changed]['net_pnl_eur'])-num(rows[control]['net_pnl_eur']) for _,rows in matched),D(0))) if matched else None,
                      'matched_symbols':[worker.cohorts[key]['symbol'] for key,_ in matched]}
    return {**common(),'schema_version':'strategy-paired-results-v1','as_of':now.isoformat(),'evaluation_day':worker.day,
            'cohort_count':len(outcomes),'pairs':pairs,
            'note':'Matched closed subsets can be selection-biased. Blocked, unfilled, open and unresolved are excluded, never treated as zero returns. Do not infer significance from correlated symbols on one day. All full-arm states are retained in report.json.'}


def historical_source(cache,symbol,now):
    from ..market_data.market_context import EXPERIMENT
    if (cache.get('protocol_id')!=EXPERIMENT or cache.get('day')!=now.astimezone(NY).date().isoformat()
        or cache.get('sha256')!=digest(cache.get('symbols'))):return {}
    sessions=[]
    for day in cache.get('sessions',[]):
        b=cache['symbols'].get(symbol,{}).get(day)
        if b is None:continue
        opening=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=NY)
        sessions.append({'open_at':opening.isoformat(),'close_at':opening.replace(hour=16,minute=0).isoformat(),
                         'volumes':b['volumes'],'sha256':digest(b['volumes']),'source_sha256':b['source_sha256']})
    return {'protocol_id':'market-context-v1','adjustment':'split','available_at':cache['saved_at'],'sessions':sessions}


def prepare(capture,news,cache,*,env,clock):
    from ..market_data.providers.alpaca_batch import fetch_histories
    from ..market_data.stock_checks import collect
    from .chart_news import checked_source
    symbols=list(dict.fromkeys(r['requested_symbol'] for r in capture['captures'] if r['market']=='stocks'))
    if len(symbols)>80:raise ValueError('strategy_capture_capacity')
    histories={}
    def history():histories.update(fetch_histories(symbols,env=env,clock=clock))
    refs=collect(symbols,env=env,clock=clock,before_quotes=history,catalogue_record=capture.get('stock_reference_checks'))
    inputs=[];failures=[]
    for symbol in symbols:
        h=histories.get(symbol)
        if not h or h.status!='ok':failures.append({'candidate_id':'stocks:'+symbol,'blockers':['fresh_chart_unavailable']});continue
        payload={**refs['payload'],'symbols':[symbol],
                 'catalogue_candidates':{symbol:refs['payload']['catalogue_candidates'].get(symbol,[])},
                 'quotes':{'currency':'USD','quotes':{symbol:refs['payload'].get('quotes',{}).get('quotes',{}).get(symbol,{})}}}
        inputs.append({'symbol':symbol,'candles':[r.model_dump(mode='json') for r in h.candles][-20:],
                       'bars_received_at':h.retrieved_at.isoformat(),'news_check':checked_source(news,symbol=symbol,now=clock()),
                       'reference_checks':{'payload':payload,'payload_sha256':digest(payload)},
                       'historical_volume':historical_source(cache,symbol,clock())})
    return inputs,failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True);parser.add_argument('--news',type=Path,required=True)
    parser.add_argument('--history',type=Path,required=True);parser.add_argument('--output',type=Path,default=Path('artifacts/strategy-experiment'))
    parser.add_argument('--duration',type=int,default=330);a=parser.parse_args()
    if not 1<=a.duration<=360:raise ValueError('bounded_strategy_duration')
    if any(os.environ.get(k) for k in ('OPENAI_API_KEY','OPEN_API_KEY','TELEGRAM_BOT_TOKEN','GH_PAPER_TOKEN')):
        raise ValueError('unneeded_credentials_forbidden')
    clock=lambda:datetime.now(UTC);local=clock().astimezone(NY)
    if local.weekday()>4 or not (9,35)<=(local.hour,local.minute)<=(16,5):
        print(json.dumps({'state':'outside_experiment_window','model_calls':0}));return 0
    def read(path,limit):
        if path.stat().st_size>limit:raise ValueError('strategy_input_capacity')
        return json.loads(path.read_text())
    capture,news=read(a.capture,12_000_000),read(a.news,8_000_000)
    cache=read(a.history,6_000_000) if a.history.is_file() else {}
    worker=StrategyExperiment(a.output,client=EventClient(os.environ.get('REVIEW_INGEST_SECRET')),clock=clock)
    start=time.monotonic();worker.sync();worker.health['startup_seconds']=round(time.monotonic()-start,3)
    inputs,failures=prepare(capture,news,cache,env=os.environ,clock=clock)
    worker.enrol(inputs,capture_sha=digest(capture),source_failures=failures)
    observer=StrategyObserver(os.environ,clock=clock);end=time.monotonic()+a.duration
    while time.monotonic()<end:
        tick=time.monotonic();worker.poll(observer)
        (a.output/'worker-health.json').write_text(canonical(worker.health)+'\n')
        remaining=end-time.monotonic()
        if remaining>0:time.sleep(min(remaining,max(.1,5-(time.monotonic()-tick))))
    report=worker.close()
    print(json.dumps({'state':'strategy_experiment_published','protocol_id':PROTOCOL_ID,'cohorts':report['cohort_count'],
                      'examined':worker.screen['examined'],'polls':worker.health['polls'],
                      'quotes_received':worker.health['quotes_received'],'error_polls':worker.health['error_polls'],
                      'model_calls':0,'trade_authorized':False}))
    if worker.health['error_polls']:print('::warning::Strategy experiment quote gaps remain in worker-health.json; outcomes may be unresolved.')
    return 0


if __name__=='__main__':raise SystemExit(main())
