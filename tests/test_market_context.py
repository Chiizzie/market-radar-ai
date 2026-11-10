from copy import deepcopy
from datetime import UTC,datetime,timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest
from market_radar_ai.market_data.market_context import collect,bins,sessions,AlpacaContext,NY,EXPERIMENT

NOW=datetime(2026,11,6,16,0,40,tzinfo=UTC)


class Provider:
    def __init__(self,now=NOW):self.now=now;self.calls=[];self.missing=False;self.early=None;self.fail=False
    def calendar(self,start,end):
        result=[]
        while start<=end:
            if start.weekday()<5:result.append({'date':start.isoformat(),'open':'09:30','close':'13:00' if start.isoformat()==self.early else '16:00'})
            start+=timedelta(days=1)
        return result
    def bars(self,symbols,start,end):
        self.calls.append((list(symbols),start,end))
        if self.fail:raise ValueError('provider detail must not escape')
        n=int((end-start).total_seconds()/300);day=start.astimezone(NY).date()
        today=day==self.now.astimezone(NY).date()
        return {s:[{'t':(start+timedelta(minutes=5*i)).astimezone(UTC).isoformat(),
                    'o':'100','h':'110','l':'90','c':str(Decimal('100')+Decimal(i+1)/100),
                    'v':200 if today else 100} for i in range(n) if not(self.missing and s=='ASH' and i==0)] for s in symbols}


def fixture():return collect(['ASH','AAPL'],client=Provider(),clock=lambda:NOW)[0]


def test_equal_elapsed_windows_and_warm_cache_only_requests_current_bars():
    p=Provider();r,cache=collect(['ASH'],client=p,clock=lambda:NOW)
    x=r['stocks'][0]
    assert r['expected_buckets']==18 and x['current_volume']=='3600'
    assert x['baseline_mean_volume']=='1800' and x['relative_volume']=='2' and x['usable_sessions']==10
    assert len(p.calls)==11 and r['bar_batch_requests']==11
    p.calls=[];r,_=collect(['ASH'],client=p,cache=cache,clock=lambda:NOW)
    assert r['history_cache_hits']==130 and len(p.calls)==1
    # Sessions straddling the US DST change retain the same New York window.
    prior=Provider();collect(['ASH'],client=prior,clock=lambda:NOW)
    assert {s.astimezone(UTC).hour for _,s,_ in prior.calls}=={13,14}


def test_early_close_baselines_are_excluded_and_current_early_close_is_capped():
    p=Provider();p.early='2026-11-05';r,_=collect(['ASH'],client=p,clock=lambda:NOW)
    assert '2026-11-05' not in [s['date'] for s in r['stocks'][0]['samples']]
    at=NOW.replace(hour=18,minute=1);p=Provider(at);p.early='2026-11-06'
    r,_=collect(['ASH'],client=p,clock=lambda:at)
    assert r['expected_buckets']==42 and r['cutoff_at']=='2026-11-06T13:00:00-05:00'


def test_missing_bars_never_become_zero_volume_or_a_price_return():
    p=Provider();p.missing=True;r,_=collect(['ASH'],client=p,clock=lambda:NOW);x=r['stocks'][0]
    assert x['observed_buckets']==17 and x['current_volume'] is None and x['return_pct'] is None
    assert x['relative_volume'] is None and x['usable_sessions']==0
    assert all(s['reason']=='missing_bars' and s['volume'] is None for s in x['samples'])


def test_calendar_failure_closed_sessions_and_incomplete_first_bucket():
    p=Provider();p.calendar=lambda *a:(_ for _ in ()).throw(ValueError('sensitive provider detail'))
    r,_=collect([],client=p,clock=lambda:NOW)
    assert r['reason']=='market_calendar_unavailable' and not p.calls and 'sensitive' not in str(r)
    p=Provider();r,_=collect([],client=p,clock=lambda:NOW+timedelta(days=1))
    assert r['reason']=='outside_regular_session' and not p.calls
    p=Provider();r,_=collect([],client=p,clock=lambda:NOW.replace(hour=14,minute=35,second=10))
    assert r['expected_buckets']==0 and r['reason']=='first_complete_bucket_pending'


def test_failed_history_is_unavailable_not_a_zero_baseline_and_is_retried():
    p=Provider();p.fail=True;r,cache=collect(['ASH'],client=p,clock=lambda:NOW)
    assert r['stocks'][0]['relative_volume'] is None and r['stocks'][0]['usable_sessions']==0
    assert r['stocks'][0]['current_source_sha256'] is None
    assert all(s['source_sha256'] is None for s in r['stocks'][0]['samples'])
    p.fail=False;p.calls=[];r,_=collect(['ASH'],client=p,cache=cache,clock=lambda:NOW)
    assert r['stocks'][0]['relative_volume']=='2' and len(p.calls)==11


@pytest.mark.parametrize('change',['hash','future','protocol','day','shape'])
def test_cache_corruption_or_wrong_date_does_not_supply_history(change):
    p=Provider();_,c=collect(['ASH'],client=p,clock=lambda:NOW)
    if change=='hash':c['sha256']='0'*64
    if change=='future':c['saved_at']=(NOW+timedelta(days=1)).isoformat()
    if change=='protocol':c['protocol_id']='0'*64
    if change=='day':c['day']='2026-11-05'
    if change=='shape':c['symbols']=[]
    p.calls=[];r,_=collect(['ASH'],client=p,cache=c,clock=lambda:NOW)
    assert r['history_cache_hits']==0 and len(p.calls)==11


@pytest.mark.parametrize("size", [40, 79, 80])
def test_all_captured_stocks_have_explicit_rows(size):
    symbols=['T'+chr(65+i//26)+chr(65+i%26) for i in range(size)]
    r,_=collect(symbols,client=Provider(),clock=lambda:NOW)
    assert len(r['stocks'])==size and len(r['benchmarks'])==12
    assert len(json.dumps(r).encode())<256000
    assert r['trade_authorized'] is False and r['strategy_input'] is False and r['model_calls']==0


def test_bar_identity_alignment_duplicates_and_future_bars_are_rejected():
    p=Provider();session=sessions(p.calendar(NOW.date(),NOW.date()),NOW.date(),NOW.date())[0]
    end=session['open']+timedelta(minutes=10);bars=p.bars(['ASH'],session['open'],end)['ASH']
    assert bins(bars,session,end)['volumes']==['200','200']
    with pytest.raises(ValueError):bins([bars[0],bars[0]],session,end)
    b=deepcopy(bars);b[0]['t']=(session['open']+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):bins(b,session,end)
    b=deepcopy(bars);b[1]['t']=end.isoformat()
    with pytest.raises(ValueError):bins(b,session,end)


def test_pagination_is_complete_and_feed_adjustment_are_explicit(monkeypatch):
    seen=[]
    def read(path,params,**kw):
        seen.append(dict(params));return {'bars':{'SPY':[]},'next_page_token':'next'} if len(seen)==1 else {'bars':{'ASH':[]}}
    monkeypatch.setattr('market_radar_ai.market_data.market_context.read',read)
    client=AlpacaContext({})
    data=client.bars(['SPY','ASH'],NOW-timedelta(minutes=5),NOW)
    assert set(data)=={'SPY','ASH'} and seen[1]['page_token']=='next'
    assert all(p['feed']=='iex' and p['adjustment']=='split' and p['asof']=='-' for p in seen)
    monkeypatch.setattr('market_radar_ai.market_data.market_context.read',lambda *a,**k:{'bars':{},'next_page_token':'same'})
    with pytest.raises(ValueError):client.bars(['SPY'],NOW-timedelta(minutes=5),NOW)


def test_historical_rehearsal_is_distinct_and_cannot_be_published(monkeypatch):
    p=Provider();r,_=collect(['ASH'],client=p,clock=lambda:NOW+timedelta(days=1),rehearsal=True)
    assert r['dataset_kind']=='historical_rehearsal' and r['session_date']=='2026-11-06'
    monkeypatch.setattr('sys.argv',['context','--publish','--rehearse-last-session'])
    from market_radar_ai.market_data.market_context import main
    with pytest.raises(SystemExit):main()


def test_full_width_context_uses_real_adapter_and_retains_all_bars(monkeypatch):
    from market_radar_ai.market_data.market_context import BENCHMARKS
    from market_radar_ai.market_data.limits import STOCK_RESEARCH_LIMIT
    symbols=['T'+chr(65+i//26)+chr(65+i%26) for i in range(STOCK_RESEARCH_LIMIT)]
    provider=Provider();requests=[]
    def read(path,params,**kwargs):
        requested=params['symbols'].split(',');requests.append(requested)
        start=datetime.fromisoformat(params['start'])
        end=datetime.fromisoformat(params['end'])+timedelta(microseconds=1)
        return {'bars':provider.bars(requested,start,end)}
    monkeypatch.setattr('market_radar_ai.market_data.market_context.read',read)
    client=AlpacaContext({});client.calendar=provider.calendar
    report,cache=collect(symbols,client=client,clock=lambda:NOW)
    assert len(requests)==11 and all(len(x)==92 for x in requests)
    assert len(report['stocks'])==80 and len(report['benchmarks'])==12
    assert all(row['relative_volume']=='2' for row in report['stocks']+report['benchmarks'])
    assert len(json.dumps(report).encode())<256000
    requests.clear()
    warm,_=collect(symbols,client=client,cache=cache,clock=lambda:NOW)
    assert warm['history_cache_hits']==920 and len(requests)==1
    with pytest.raises(ValueError,match='invalid_batch_symbols'):
        collect(symbols+['EXTRA'],client=client,clock=lambda:NOW)
    with pytest.raises(ValueError,match='invalid_batch_symbols'):
        client.bars(list(BENCHMARKS)+symbols+['EXTRA'],NOW-timedelta(minutes=5),NOW)
    monkeypatch.setattr('market_radar_ai.market_data.market_context.read',
                        lambda *a,**k:{'bars':{'SPY':[{}]*79}})
    with pytest.raises(ValueError,match='context_bar_capacity'):
        client.bars(['SPY'],NOW-timedelta(minutes=5),NOW)
