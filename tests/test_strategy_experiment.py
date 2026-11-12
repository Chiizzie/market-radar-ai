"""Synthetic offline tests only. No provider, notification or production writes."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.comparison_live import event_id
from market_radar_ai.agents.strategy_experiment import (
    D, PROTOCOL, PROTOCOL_ID, VARIANTS, build, economics, fees, historical_volume, replay, summarize,
)
from market_radar_ai.agents.strategy_experiment_live import StrategyExperiment, StrategyObserver, historical_source
from market_radar_ai.market_data.models import Candle

NOW=datetime(2026,11,12,16,10,1,tzinfo=UTC)


def fixture():
    bars=[]
    for i in range(20):
        close=D(100)+D(i)/10
        bars.append({'symbol':'TEST','interval':'5m','timestamp':(NOW.replace(hour=14,minute=30,second=0)+timedelta(minutes=5*i)).isoformat(),
                     'open':str(close-D('.05')),'close':str(close),'high':str(close+D('.6')),'low':str(close-D('.6')),
                     'volume':'20000' if i>=15 else '10000','quote_currency':'USD','source':'alpaca_iex'})
    refs={'schema_version':'stock-reference-checks-v1','symbols':['TEST'],'trade_authorized':False,'retrieved_at':NOW.isoformat(),
          'catalogue_candidates':{'TEST':[{'ticker':'TEST_US_EQ','isin':'test'}]},
          'market_clock':{'is_open':True,'timestamp':NOW.isoformat(),'next_close':'2026-11-12T21:00:00Z','next_open':'2026-11-13T14:30:00Z'},
          'fx':{'native_currency':'USD','eur_per_unit':'0.9','observed_at':NOW.isoformat(),'source':'synthetic'},
          'quotes':{'currency':'USD','quotes':{'TEST':{'t':NOW.isoformat(),'bp':101.90,'ap':101.95,'bs':100,'as':100}}}}
    sessions=[]
    for day in ['2026-10-29','2026-10-30','2026-11-02','2026-11-03','2026-11-04','2026-11-05','2026-11-06','2026-11-09','2026-11-10','2026-11-11']:
        offset='-04:00' if day<'2026-11-01' else '-05:00';vols=['10000']*78
        sessions.append({'open_at':day+'T09:30:00'+offset,'close_at':day+'T16:00:00'+offset,
                         'volumes':vols,'sha256':digest(vols),'source_sha256':'a'*64})
    return {'symbol':'TEST','candles':bars,'bars_received_at':NOW.isoformat(),
            'reference_checks':{'payload':refs,'payload_sha256':digest(refs)},
            'news_check':{'schema_version':'chart-news-check-v1','query_symbol':'TEST','status':'checked_bounded_source',
                          'scope':'PUBLISHER_TAGGED_STOCK_NEWS_PARTIAL','checked_at':NOW.isoformat(),'validated_item_count':0,
                          'coverage_complete':False,'fresh_catalyst_required':False},
            'historical_volume':{'protocol_id':'market-context-v1','adjustment':'split','available_at':NOW.isoformat(),'sessions':sessions}}


def cohort():
    return {**build(fixture(),now=NOW),'enrolled_at':NOW.isoformat()}


def observation(bid,ask=None,*,seconds=1,exchange=None,durable=None):
    at=NOW+timedelta(seconds=seconds)
    return {'received_at':at.isoformat(),'durable_received_at':(durable or at).isoformat(),
            'quote':{'observed_at':(exchange or at).isoformat(),'bid':str(bid),'ask':str(ask if ask is not None else bid)}}


def test_frozen_matrix_recomputes_net_risk_currency_and_allocation():
    s=build(fixture(),now=NOW)
    assert s['blockers']==[]
    assert set(s['variants'])==set(VARIANTS) and len(VARIANTS)==10
    for name,v in s['variants'].items():
        p=v['plan'];e=economics(p,VARIANTS[name]['cost'])
        assert D(p['planned_loss_eur'])==e['risk']<=20
        assert D(p['reserved_capital_eur'])==e['capital']<=500
        assert D(p['entry_usd'])*D(p['fx_rate'])==D(p['entry_eur'])
        if not v['blockers']:assert e['rr']>=D('1.999999')
    assert s['features']['same_time_volume']['ratio']=='2'
    assert D(s['features']['atr14_usd'])==D('1.2')
    assert D(s['variants']['same_time_atr_usd']['plan']['stop_usd'])<D(s['variants']['same_time_structural_usd']['plan']['stop_usd'])
    assert s['source_sha256']==digest(fixture()) and not s['trade_authorized']


def test_same_time_volume_handles_opening_surge_and_DST_without_filling_gaps():
    f=fixture()
    for r in f['candles'][:15]:r['volume']='100000'
    s=build(f,now=NOW)
    assert s['blockers']==[]
    assert 'relative_volume_below_one' in s['variants']['rolling_structural_usd']['blockers']
    assert s['variants']['same_time_structural_usd']['blockers']==[]
    assert s['features']['same_time_volume']['usable_sessions']==10
    for session in f['historical_volume']['sessions'][:6]:
        session['volumes'][18]=None;session['sha256']=digest(session['volumes'])
    s=build(f,now=NOW)
    assert s['features']['same_time_volume']['ratio'] is None
    assert s['features']['same_time_volume']['usable_sessions']==4
    assert 'same_time_volume_unavailable' in s['variants']['same_time_structural_usd']['blockers']


@pytest.mark.parametrize('fault',['future_day','duplicate_day','short_day','future_receipt','bad_hash','negative_volume'])
def test_noncausal_or_corrupt_historical_data_never_falls_back(fault):
    f=fixture();s=f['historical_volume'];x=s['sessions'][-1]
    if fault=='future_day':x['open_at']='2026-11-12T09:30:00-05:00';x['close_at']='2026-11-12T16:00:00-05:00'
    if fault=='duplicate_day':s['sessions'][-1]=deepcopy(s['sessions'][-2])
    if fault=='short_day':x['close_at']='2026-11-11T13:00:00-05:00'
    if fault=='future_receipt':s['available_at']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='bad_hash':x['volumes'][18]='200000'
    if fault=='negative_volume':x['volumes'][18]='-1';x['sha256']=digest(x['volumes'])
    r=build(f,now=NOW)
    assert r['features']['same_time_volume']['ratio'] is None
    assert r['variants']['rolling_structural_usd']['blockers']==[]


@pytest.mark.parametrize('fault,reason',[
    ('future_bar','invalid_bars'),('gap','incomplete_bar_window'),('short','twenty_completed_bars_required'),
    ('stale_bars','stale_bar_receipt'),('news','news_risk_check_unavailable'),
    ('stale_quote','broker_catalogue_or_reference_unavailable'),('wide','reference_spread_over_20bps'),
    ('closed','reference_clock_or_fx_unavailable'),('future_fx','reference_clock_or_fx_unavailable')])
def test_common_invalid_sources_never_create_variants(fault,reason):
    f=fixture();p=f['reference_checks']['payload']
    if fault=='future_bar':f['candles'][-1]['timestamp']=NOW.isoformat()
    if fault=='gap':f['candles'][3]['timestamp']=f['candles'][2]['timestamp']
    if fault=='short':f['candles'].pop()
    if fault=='stale_bars':f['bars_received_at']=(NOW-timedelta(seconds=61)).isoformat()
    if fault=='news':f['news_check']=None
    if fault=='stale_quote':p['quotes']['quotes']['TEST']['t']=(NOW-timedelta(seconds=31)).isoformat()
    if fault=='wide':p['quotes']['quotes']['TEST']['bp']=95
    if fault=='closed':p['market_clock']['is_open']=False
    if fault=='future_fx':p['fx']['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
    f['reference_checks']['payload_sha256']=digest(p)
    s=build(f,now=NOW);assert reason in s['blockers'];assert not s['variants']


def test_usd_eur_stress_costs_are_distinct_and_spread_is_not_a_second_fee():
    usd=fees('usd',D(100),D(105),D(4),D('.9'))
    eur=fees('eur',D(100),D(105),D(4),D('.9'))
    assert usd['entry_fx_eur']==usd['exit_fx_eur']==0
    assert eur['entry_fx_eur']==D('.60') and eur['exit_fx_eur']==D('.63')
    assert set(usd)=={'entry_fx_eur','exit_fx_eur','sale_levies_eur'}
    s=cohort();p=s['variants']['same_time_atr_usd']['plan'];entry=D(p['entry_eur']);target=D(p['target_eur'])
    r=replay(s,[observation(entry-D('.01'),entry),observation(target,target+D('.01'),seconds=6)],now=NOW+timedelta(seconds=7))['same_time_atr_usd']
    assert r['state']=='closed'
    q=D(p['quantity']);fx=D(p['fx_rate']);fill_in=entry*D('1.0005');fill_out=target*D('.9995')
    expected=(fill_out-fill_in)*q-sum(fees('usd',fill_in,fill_out,q,fx).values())
    assert D(r['net_pnl_eur'])==expected
    assert D(r['slippage_eur'])>0


def test_wide_quotes_do_not_invalidate_entry_or_create_fake_profit():
    s=cohort();p=s['variants']['same_time_atr_usd']['plan'];e=D(p['entry_eur']);stop=D(p['stop_eur']);target=D(p['target_eur'])
    quotes=[observation(stop-5,e+5),observation(e,seconds=6),observation(target,target+10,seconds=11),observation(target+1,seconds=16)]
    r=replay(s,quotes,now=NOW+timedelta(seconds=20))['same_time_atr_usd']
    assert r['state']=='unresolved' and r['reason']=='exit_quote_quality_unresolved'
    assert r['entry_at']==(NOW+timedelta(seconds=6)).isoformat() and r['net_pnl_eur'] is None
    assert r['rejected_wide_quotes']==2


def test_late_receipt_cannot_backdate_entry_and_no_same_quote_exit():
    s=cohort();p=s['variants']['same_time_atr_usd']['plan'];e=D(p['entry_eur'])
    delayed=observation(e,seconds=179,durable=NOW+timedelta(seconds=181))
    assert replay(s,[delayed],now=NOW+timedelta(seconds=182))['same_time_atr_usd']['state']=='not_filled'
    r=replay(s,[observation(e)],now=NOW+timedelta(seconds=2))['same_time_atr_usd']
    assert r['state']=='open' and r['exit_at'] is None


def test_missing_or_one_second_late_exit_stays_unresolved():
    s=cohort();p=s['variants']['same_time_atr_usd']['plan'];e=D(p['entry_eur']);deadline=datetime.fromisoformat(p['exit_by'])
    quotes=[observation(e),observation(e+1,seconds=int((deadline-NOW).total_seconds())+1)]
    r=replay(s,quotes,now=deadline+timedelta(seconds=2))['same_time_atr_usd']
    assert r['state']=='unresolved' and r['net_pnl_eur'] is None
    ontime=observation(e+1,seconds=int((deadline-NOW).total_seconds())-5)
    r=replay(s,[quotes[0],ontime],now=deadline)['same_time_atr_usd']
    assert r['state']=='closed' and r['reason']=='scheduled_exit'


def test_before_enrolment_stale_and_future_quotes_cannot_fill():
    s=cohort();p=s['variants']['same_time_atr_usd']['plan'];e=D(p['entry_eur'])
    for o in [observation(e,seconds=-1),observation(e,seconds=61,exchange=NOW-timedelta(seconds=1)),observation(e,seconds=200)]:
        assert replay(s,[o],now=NOW+timedelta(seconds=100))['same_time_atr_usd']['state']=='watching'


class Events:
    def __init__(self):self.events=[];self.fail=False;self.delay=0
    def append(self,experiment,events):
        if self.fail:raise RuntimeError('storage_failed')
        for e in events:
            eid=event_id(experiment,e)
            if any(r['event_id']==eid for r in self.events):continue
            self.events.append({**e,'event_id':eid,'experiment_id':experiment,'day':e['occurred_at'][:10],
                                'seq':len(self.events)+1,'received_at':(datetime.fromisoformat(e['occurred_at'])+timedelta(seconds=self.delay)).isoformat()})
    def read(self,experiment,day,after):
        if self.fail:raise RuntimeError('storage_failed')
        events=[e for e in self.events if e['seq']>after][:3]
        return {'events':events,'next':events[-1]['seq'] if events else after}


def test_durable_cohort_is_frozen_across_restart_and_repeated_capture(tmp_path):
    client=Events();t=[NOW];w=StrategyExperiment(tmp_path/'one',client=client,clock=lambda:t[0])
    w.enrol([fixture()],capture_sha='a'*64)
    first=deepcopy(w.cohorts);t[0]+=timedelta(seconds=5)
    f=fixture();f['candles'][-1]['volume']='30000'
    w.enrol([f],capture_sha='b'*64)
    assert w.cohorts==first
    assert w.screen['reasons']=={'already_frozen_this_session':1}
    r=w.close();other=StrategyExperiment(tmp_path/'two',client=client,clock=lambda:t[0]);other.sync()
    assert other.cohorts==first and other.report()['variants']==r['variants']
    assert all(v['net_pnl_eur'] is None for v in r['variants'].values())


def test_delayed_enrolment_and_failed_storage_cannot_create_fills(tmp_path):
    client=Events();client.delay=181;w=StrategyExperiment(tmp_path/'one',client=client,clock=lambda:NOW)
    w.enrol([fixture()],capture_sha='a'*64)
    assert all(r['state'] in ('blocked','not_filled') for r in next(iter(w.outcomes(NOW+timedelta(seconds=182)).values())).values())
    client.fail=True
    with pytest.raises(RuntimeError):w.poll(SimpleNamespace(fetch=lambda _:pytest.fail('no network before sync')))
    assert w.health['quotes_received']==0


def test_tampered_cohort_and_currency_are_refused(tmp_path):
    client=Events();w=StrategyExperiment(tmp_path/'one',client=client,clock=lambda:NOW);w.enrol([fixture()],capture_sha='a'*64)
    e=deepcopy(client.events[0]);p=json.loads(e['payload_json']);p['cohort']['features']['atr14_usd']='999'
    e['payload_json']=json.dumps(p);e['event_id']=event_id(PROTOCOL_ID,e)
    other=StrategyExperiment(tmp_path/'two',client=client,clock=lambda:NOW)
    with pytest.raises(ValueError,match='cohort_replay'):other.apply(e)


def test_summary_keeps_missing_results_null_and_arms_separate():
    r=summarize([{'state':'unresolved'},{'state':'not_filled'}])
    assert r['closed']==0 and r['net_pnl_eur'] is None and r['closed_drawdown_eur'] is None
    rows=[{'state':'closed','net_pnl_eur':p,'fee_eur':'.1','slippage_eur':'.2','exit_at':str(i)} for i,p in enumerate(['10','-12','3'])]
    assert summarize(rows)['closed_drawdown_eur']=='12'


def test_fees_expire_and_protocol_is_pinned():
    assert PROTOCOL_ID=='c796287f67ef1be3a30d2dcdb1cdea8183e8ec75eb34a5bc9885b480ad2059b1'
    assert build(fixture(),now=datetime(2026,12,14,16,tzinfo=UTC))['blockers']==['experiment_or_fee_window_closed']


def test_native_observer_uses_frozen_fx_and_durable_quotes_replay(tmp_path,monkeypatch):
    from market_radar_ai.market_data import stock_checks
    t=[NOW];client=Events();worker=StrategyExperiment(tmp_path/'one',client=client,clock=lambda:t[0])
    worker.enrol([fixture()],capture_sha='a'*64)
    c=next(iter(worker.cohorts.values()));p=c['variants']['same_time_atr_usd']['plan'];price=[D(p['entry_usd'])]
    def get(url,params,env,session):
        if url==stock_checks.CLOCK:return {'is_open':True,'timestamp':t[0].isoformat()}
        assert url==stock_checks.QUOTES and params['currency']=='USD' and params['feed']=='iex'
        return {'quotes':{'TEST':{'t':t[0].isoformat(),'bp':str(price[0]),'ap':str(price[0]),'bs':100,'as':100}}}
    monkeypatch.setattr(stock_checks,'get',get)
    observer=StrategyObserver({},clock=lambda:t[0]);t[0]+=timedelta(seconds=1);worker.poll(observer)
    assert next(iter(worker.outcomes(t[0]).values()))['same_time_atr_usd']['state']=='open'
    price[0]=D(p['target_usd']);t[0]+=timedelta(seconds=5);worker.poll(observer)
    r=worker.close();assert r['variants']['same_time_atr_usd']['closed']==1
    quote=next(json.loads(e['payload_json']) for e in client.events if e['kind']=='quote')
    assert quote['eur_per_usd']=='0.9' and quote['protocol_id']==PROTOCOL_ID and quote['model_calls']==0
    other=StrategyExperiment(tmp_path/'two',client=client,clock=lambda:t[0]);other.sync()
    assert other.report()['variants']==r['variants']
    assert json.loads((tmp_path/'one/paired-results.json').read_text())['pairs']['risk_with_same_time_usd']['matched_closed']>=0
    tampered=deepcopy(next(e for e in client.events if e['kind']=='quote'))
    payload=json.loads(tampered['payload_json']);payload['eur_per_usd']='1.1';tampered['payload_json']=json.dumps(payload)
    tampered['event_id']=event_id(PROTOCOL_ID,tampered)
    with pytest.raises(ValueError,match='fx_mismatch'):other.apply(tampered)


def test_observer_retains_unknown_or_stale_quotes_as_gaps(monkeypatch):
    from market_radar_ai.market_data import stock_checks
    def get(url,params,env,session):
        if url==stock_checks.CLOCK:return {'is_open':True,'timestamp':NOW.isoformat()}
        return {'quotes':{'TEST':{'t':(NOW-timedelta(seconds=31)).isoformat(),'bp':100,'ap':100.1,'bs':100,'as':100}}}
    monkeypatch.setattr(stock_checks,'get',get)
    assert StrategyObserver({},clock=lambda:NOW).fetch([cohort()])==([],['quote_unavailable:TEST'])


def test_report_bounds_preserve_aggregate_counts(tmp_path):
    worker=StrategyExperiment(tmp_path/'one',client=Events(),clock=lambda:NOW)
    for i in range(40):
        c=cohort();c['setup_id']=digest(str(i));c['candidate_id']='stocks:T'+str(i);c['symbol']='T'+str(i)
        for v in c['variants'].values():v['plan']['symbol']=c['symbol']
        worker.cohorts[c['setup_id']]=c
    r=worker.report()
    assert r['cohort_count']==40 and len(r['rows'])+r['rows_omitted']==400
    assert len(json.dumps(r).encode())<180000
    assert all(sum(v['states'].values())==40 for v in r['variants'].values())
