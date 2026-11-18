"""Independent market/sector and same-time IEX volume research. No trade admission."""
import argparse
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from .providers.alpaca_batch import read, symbols_checked
from .stock_checks import get
from ..agents.candidate_packages import canonical, digest

NY=ZoneInfo('America/New_York'); D=Decimal
BENCHMARKS={'SPY':'Broad US large-cap market','XLC':'Communication services',
 'XLY':'Consumer discretionary','XLP':'Consumer staples','XLE':'Energy','XLF':'Financials',
 'XLV':'Health care','XLI':'Industrials','XLB':'Materials','XLRE':'Real estate',
 'XLK':'Technology','XLU':'Utilities'}
PROTOCOL={'version':'market-context-v1','feed':'iex','adjustment':'split','bar_minutes':5,
 'baseline_sessions':10,'minimum_sessions':5,'settling_seconds':30,'cache_symbols':400,
 'benchmark_symbols':list(BENCHMARKS),'strategy_input':False}
EXPERIMENT=digest(PROTOCOL)
CALENDAR='https://paper-api.alpaca.markets/v2/calendar'


def aware(s):
    t=datetime.fromisoformat(s.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('aware_context_time_required')
    return t


def amount(v, *, positive=False):
    if isinstance(v,bool):raise ValueError('invalid_context_amount')
    d=D(str(v))
    if not d.is_finite() or d<0 or (positive and d==0) or d>D('1e18'):
        raise ValueError('invalid_context_amount')
    return format(d,'f')


def sessions(raw, start, end):
    if not isinstance(raw,list) or len(raw)>36:raise ValueError('invalid_calendar')
    rows=[]; seen=set()
    for r in raw:
        day=date.fromisoformat(r['date'])
        opening=datetime.fromisoformat(r['date']+'T'+r['open']).replace(tzinfo=NY)
        close=datetime.fromisoformat(r['date']+'T'+r['close']).replace(tzinfo=NY)
        if (not start<=day<=end or day in seen or day.weekday()>4 or r['open']!='09:30'
                or not opening<close<=opening.replace(hour=16,minute=0)
                or (close-opening).total_seconds()%300):raise ValueError('unsupported_calendar_session')
        seen.add(day);rows.append({'date':day.isoformat(),'open':opening,'close':close})
    return sorted(rows,key=lambda x:x['date'])


class AlpacaContext:
    def __init__(self,env,session=None):self.env=env;self.session=session or requests.Session()
    def calendar(self,start,end):
        return get(CALENDAR,{'start':start.isoformat(),'end':end.isoformat()},self.env,self.session)
    def bars(self,symbols,start,end):
        symbols=symbols_checked(symbols,52)
        params={'symbols':','.join(symbols),'timeframe':'5Min','start':start.isoformat(),
          'end':(end-timedelta(microseconds=1)).isoformat(),'feed':'iex','adjustment':'split',
          'asof':'-','currency':'USD','sort':'asc','limit':10000}
        output={};tokens=set()
        for _ in range(8):
            data=read('bars',params,env=self.env,session=self.session)
            bars=data.get('bars')
            if not isinstance(bars,dict) or set(bars)-set(symbols) or any(not isinstance(v,list) for v in bars.values()):
                raise ValueError('context_bar_identity')
            for symbol,items in bars.items():output.setdefault(symbol,[]).extend(items)
            if sum(map(len,output.values()))>52*78:raise ValueError('context_bar_capacity')
            token=data.get('next_page_token')
            if not token:return output
            if not isinstance(token,str) or len(token)>1000 or token in tokens:raise ValueError('context_pagination')
            tokens.add(token);params['page_token']=token
        raise ValueError('context_pagination_incomplete')


def bins(raw, session, cutoff):
    """Missing provider bars remain null, never zero-volume observations."""
    n=int((cutoff-session['open']).total_seconds()/300)
    if not 1<=n<=78 or not isinstance(raw,list) or len(raw)>78:raise ValueError('invalid_context_window')
    volumes=[None]*n; opening=closing=None;previous=None
    for b in raw:
        t=aware(b['t']);delta=(t-session['open']).total_seconds()
        if delta<0 or delta%300 or t>=cutoff or (previous and t<=previous):raise ValueError('context_bar_time')
        previous=t;index=int(delta/300)
        o,h,l,c=[D(amount(b[k],positive=True)) for k in ('o','h','l','c')]
        if not l<=min(o,c)<=max(o,c)<=h:raise ValueError('context_bar_ohlc')
        volumes[index]=amount(b['v'])
        if index==0:opening=format(o,'f')
        if index==n-1:closing=format(c,'f')
    return {'volumes':volumes,'open_usd':opening,'last_usd':closing,'source_sha256':digest(raw)}


def cache_valid(cache, *, day, prior, now):
    try:
        if (cache['schema_version']!='market-context-cache-v1' or cache['protocol_id']!=EXPERIMENT
                or cache['day']!=day or cache['sessions']!=[s['date'] for s in prior]
                or cache['sha256']!=digest(cache['symbols']) or aware(cache['saved_at'])>now
                or len(cache['symbols'])>400):return {}
        symbols_checked(cache['symbols'],400)
        for by_day in cache['symbols'].values():
            if set(by_day)-set(cache['sessions']):raise ValueError('cache_session')
            for value in by_day.values():
                if len(value['volumes'])!=78 or not re.fullmatch('[a-f0-9]{64}',value['source_sha256']):raise ValueError('cache_shape')
                for v in value['volumes']:
                    if v is not None:amount(v)
                for field in ('open_usd','last_usd'):
                    if value[field] is not None:amount(value[field],positive=True)
        return cache['symbols']
    except (KeyError,ValueError,TypeError,ArithmeticError,AttributeError):return {}


def row(symbol,current,history,prior,n):
    vols=current['volumes'] if current else [None]*n
    observed=sum(v is not None for v in vols)
    complete=n>0 and observed==n
    total=sum((D(v) for v in vols),D(0)) if complete else None
    opening=current['open_usd'] if complete else None
    close=current['last_usd'] if complete else None
    samples=[]
    for day in prior:
        b=history.get(day['date']); values=b['volumes'][:n] if b else []
        count=sum(v is not None for v in values)
        usable=n>0 and len(values)==n and count==n
        samples.append({'date':day['date'],'observed_buckets':count,
          'volume':format(sum((D(v) for v in values),D(0)),'f') if usable else None,
          'source_sha256':b['source_sha256'] if b else None,
          'reason':None if usable else 'missing_bars' if b else 'provider_unavailable'})
    usable=[D(s['volume']) for s in samples if s['volume'] is not None]
    mean=sum(usable,D(0))/len(usable) if len(usable)>=5 else None
    ratio=total/mean if total is not None and mean is not None and mean>0 else None
    return {'symbol':symbol,'label':BENCHMARKS.get(symbol,symbol),'observed_buckets':observed,
      'current_source_sha256':current['source_sha256'] if current else None,
      'open_usd':opening,'last_usd':close,
      'return_pct':format((D(close)/D(opening)-1)*100,'f') if opening and close else None,
      'current_volume':format(total,'f') if total is not None else None,
      'samples':samples,'usable_sessions':len(usable),
      'baseline_mean_volume':format(mean,'f') if mean is not None else None,
      'relative_volume':format(ratio,'f') if ratio is not None else None,
      'volume_reason':None if ratio is not None else 'current_window_incomplete' if not complete else
          'insufficient_history' if mean is None else 'zero_baseline'}


def collect(symbols, *, client, cache=None, clock=lambda:datetime.now(UTC), capture_sha=None, rehearsal=False):
    from .limits import STOCK_RESEARCH_LIMIT
    symbols=symbols_checked(symbols,STOCK_RESEARCH_LIMIT) if symbols else []
    now=clock()
    if now.tzinfo is None:raise ValueError('aware_context_clock_required')
    local=now.astimezone(NY); calendar=[];cal_hash=None;failure=None
    try:
        raw=client.calendar(local.date()-timedelta(days=35),local.date())
        calendar=sessions(raw,local.date()-timedelta(days=35),local.date());cal_hash=digest(raw)
    except Exception:failure='market_calendar_unavailable'
    today=next((s for s in calendar if s['date']==local.date().isoformat()),None)
    if rehearsal:
        today=next((s for s in reversed(calendar) if s['close']<now),None)
    prior=[s for s in calendar if today and s['date']<today['date'] and (s['close']-s['open'])==timedelta(hours=6,minutes=30)][-10:]
    day=local.date().isoformat()
    cached=cache_valid(cache or {},day=day,prior=prior,now=now)
    wanted=list(dict.fromkeys([*BENCHMARKS,*symbols]));hits=0;requests_count=0
    active=today is not None and (rehearsal or today['open']<=now<=today['close']+timedelta(minutes=15))
    if active:
        for session in prior:
            missing=[s for s in wanted if session['date'] not in cached.get(s,{})]
            hits+=len(wanted)-len(missing)
            if not missing:continue
            requests_count+=1
            try:data=client.bars(missing,session['open'],session['close'])
            except Exception:continue
            for s in missing:
                try:
                    b=bins(data.get(s,[]),session,session['close'])
                    cached.setdefault(s,{})[session['date']]=b
                except (ValueError,TypeError,KeyError,ArithmeticError):pass
    # Long historical reads finish before choosing the current complete window.
    now=clock();cutoff=None;n=0;current={}
    if active:
        elapsed=(today['close']-today['open']).total_seconds() if rehearsal else (min(now-timedelta(seconds=30),today['close'])-today['open']).total_seconds()
        n=max(0,min(78,int(elapsed//300)));cutoff=today['open']+timedelta(minutes=5*n) if n else None
        if cutoff:
            requests_count+=1
            try:data=client.bars(wanted,today['open'],cutoff)
            except Exception:data=None;failure='current_bars_unavailable'
            for s in wanted:
                if data is None:continue
                try:current[s]=bins(data.get(s,[]),today,cutoff)
                except (ValueError,TypeError,KeyError,ArithmeticError):pass
    rows={s:row(s,current.get(s),cached.get(s,{}),prior,n) for s in wanted}
    report={'schema_version':'market-context-report-v1','protocol_id':EXPERIMENT,'as_of':clock().isoformat(),
      'evaluation_day':clock().date().isoformat(),'dataset_kind':'historical_rehearsal' if rehearsal else 'forward',
      'trade_authorized':False,'strategy_input':False,'model_calls':0,'feed':'iex','adjustment':'split',
      'session_date':today['date'] if today else day,'session_open_at':today['open'].isoformat() if today else None,
      'session_close_at':today['close'].isoformat() if today else None,'cutoff_at':cutoff.isoformat() if cutoff else None,
      'expected_buckets':n,'baseline_target_sessions':10,'minimum_sessions':5,'calendar_sha256':cal_hash,
      'capture_sha256':capture_sha,'requested_stocks':symbols,'benchmarks':[rows[s] for s in BENCHMARKS],
      'stocks':[rows[s] for s in symbols], 'history_cache_hits':hits,'bar_batch_requests':requests_count,
      'reason':failure or ('outside_regular_session' if not active else 'first_complete_bucket_pending' if not n else None),
      'note':'Research observations only. IEX is a partial venue, not consolidated market volume. '
          'Returns run from the first regular-session bar open to the same completed bar close; overnight gaps are excluded. '
          'Volume compares that identical elapsed window with up to ten prior full sessions, requiring five complete samples. '
          'Missing bars are unknown, never zero. Split-adjusted history is refreshed each date. '
          'Sector ETFs are comparison benchmarks; individual company sector membership is not verified. '
          'This evidence is available only at its report time and is not fed into existing trade rules or AI prompts.'}
    keep=list(dict.fromkeys([*wanted,*cached]))[:400]
    values={s:cached[s] for s in keep if s in cached}
    saved={'schema_version':'market-context-cache-v1','protocol_id':EXPERIMENT,'day':day,
      'sessions':[s['date'] for s in prior],'symbols':values,'saved_at':clock().isoformat(),'sha256':digest(values)}
    return report,saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path);p.add_argument('--symbols',default='')
    p.add_argument('--output',type=Path,default=Path('artifacts/market-context'))
    p.add_argument('--cache',type=Path,default=Path('.scanner-cache/market-context.json'))
    p.add_argument('--publish',action='store_true');p.add_argument('--rehearse-last-session',action='store_true')
    a=p.parse_args()
    if a.publish and a.rehearse_last_session:p.error('Historical rehearsals cannot be published as forward evidence')
    symbols=[s for s in a.symbols.split(',') if s];capture_sha=None
    if a.capture:
        if a.capture.stat().st_size>8_000_000:raise ValueError('capture_capacity')
        raw=a.capture.read_text();doc=json.loads(raw);capture_sha=digest(doc)
        symbols=list(dict.fromkeys(c['requested_symbol'] for c in doc['captures'] if c['market']=='stocks'))
    cache={}
    if a.cache.is_file() and a.cache.stat().st_size<=6_000_000:
        try:cache=json.loads(a.cache.read_text())
        except ValueError:pass
    report,saved=collect(symbols,client=AlpacaContext(os.environ),cache=cache,rehearsal=a.rehearse_last_session)
    a.output.mkdir(parents=True,exist_ok=True);(a.output/'report.json').write_text(canonical(report)+'\n')
    a.cache.parent.mkdir(parents=True,exist_ok=True)
    raw=canonical(saved)
    if len(raw.encode())<=6_000_000:a.cache.write_text(raw+'\n')
    if a.publish:
        from ..agents.comparison_live import EventClient,envelope
        EventClient(os.environ.get('REVIEW_INGEST_SECRET')).append(EXPERIMENT,[envelope('context_report',report,aware(report['as_of']))])
    print(json.dumps({'state':'context_published' if a.publish else 'historical_rehearsal' if a.rehearse_last_session else 'context_collected',
      'session_date':report['session_date'],'stocks':len(symbols),'benchmarks':len(BENCHMARKS),
      'measured_stock_volume':sum(r['relative_volume'] is not None for r in report['stocks']),
      'measured_benchmark_volume':sum(r['relative_volume'] is not None for r in report['benchmarks']),
      'history_cache_hits':report['history_cache_hits'],'bar_batch_requests':report['bar_batch_requests'],
      'reason':report['reason'],'model_calls':0,'trade_authorized':False}))


if __name__=='__main__':main()
