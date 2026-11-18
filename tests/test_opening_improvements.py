from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
import json

from test_method_shadow import fixture, NOW
from test_comparison_live import MemoryEvents
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.early_opening import scenario, PROTOCOL_ID
from market_radar_ai.agents.method_shadow import MethodShadow, screen_capture
from market_radar_ai.market_data.coverage_lanes import CORE, leaders, reserve_screen, select_details
from market_radar_ai.dashboard.missed_moves import explain


def early_input():
    i=fixture();t=NOW.replace(hour=14,minute=45)
    i['candles']=i['candles'][:3]
    for c in i['candles']: c['volume']='100000'
    i['candles'][0]['low']='97'
    i['context']['retrieved_at']=i['bars_received_at']=t.isoformat()
    i['news_check']['checked_at']=t.isoformat()
    p=i['reference_checks']['payload'];p['retrieved_at']=t.isoformat()
    p['market_clock']['timestamp']=p['fx']['observed_at']=t.isoformat()
    p['quotes']['quotes']['TEST'].update(t=t.isoformat(),bp=99.4,ap=99.45)
    i['reference_checks']['payload_sha256']=digest(p)
    return i,t


def test_early_separate_risk_causal_fill_exit_restore(tmp_path):
    i,t=early_input();s=scenario(i,now=t)
    assert not s['blockers'],s['blockers']
    p=s['plan'];risk=(Decimal(p['entry_eur'])-Decimal(p['stop_eur']))*Decimal(p['quantity'])+Decimal(p['assumed_round_trip_cost_eur'])
    assert 0<risk<=20
    assert s['protocol_id']==PROTOCOL_ID
    client=MemoryEvents();at=[t];price=[p['entry_eur']]
    obs=SimpleNamespace(fetch=lambda ds:([{'packet_id':d['packet_id'],'source':'alpaca_iex:'+'a'*64,
        'quote':{'observed_at':at[0].isoformat(),'bid':price[0],'ask':price[0]}} for d in ds],[]))
    w=MethodShadow(tmp_path/'first',client=client,observer=obs,clock=lambda:at[0],early_opening=True)
    assert w.enrol(i,now=t)==[]
    at[0]+=timedelta(seconds=2);w.poll()
    assert w.outcomes(at[0])[0]['state']=='open_simulation'
    price[0]=p['target_eur'];at[0]+=timedelta(seconds=2);w.poll();w.close()
    assert w.outcomes(at[0])[0]['state']=='closed'
    assert (tmp_path/'first/early-opening-report.json').exists()
    assert not any(e['kind']=='method_report' for e in client.events)
    w2=MethodShadow(tmp_path/'restore',client=client,clock=lambda:at[0],early_opening=True);w2.sync()
    assert w2.outcomes(at[0])==w.outcomes(at[0])
    assert w2.enrol(i,now=at[0])==['already_enrolled_this_session']
    regular=MethodShadow(tmp_path/'regular',client=client,clock=lambda:at[0]);regular.sync()
    assert not regular.cohorts


def test_early_rejects_before_window_future_bars_gaps_and_passed_trigger():
    i,t=early_input()
    from market_radar_ai.agents.early_opening import measure
    assert measure(i['candles'],i['daily'],symbol='TEST',now=t-timedelta(minutes=1))['blockers']
    assert measure(i['candles'],i['daily'],symbol='TEST',now=t+timedelta(minutes=15))['blockers']
    for change in ('gap','future','symbol','stale','quote'):
        v=deepcopy(i)
        if change=='gap':v['candles']=v['candles'][1:]
        if change=='future':v['candles'][-1]['timestamp']=t.isoformat()
        if change=='symbol':v['candles'][0]['symbol']='OTHER'
        if change=='stale':v['bars_received_at']=(t-timedelta(seconds=61)).isoformat()
        if change=='quote':
            v['reference_checks']['payload']['quotes']['quotes']['TEST']['ap']=102
            v['reference_checks']['payload_sha256']=digest(v['reference_checks']['payload'])
        assert scenario(v,now=t)['blockers'],change


def test_slow_metadata_precedes_history_and_quotes(monkeypatch,tmp_path):
    i=fixture();at=[NOW];events=MemoryEvents()
    w=MethodShadow(tmp_path/'worker',client=events,clock=lambda:at[0])
    def fetch(symbols,**kw):
        assert at[0]==NOW+timedelta(seconds=106)
        return {'TEST':SimpleNamespace(status='ok',retrieved_at=at[0],candles=[])}
    def collect(symbols,*,before_quotes,**kw):
        at[0]+=timedelta(seconds=106);before_quotes()
        return i['reference_checks']
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.fetch_histories',fetch)
    monkeypatch.setattr('market_radar_ai.market_data.stock_checks.collect',collect)
    monkeypatch.setattr('market_radar_ai.agents.chart_news.checked_source',lambda *a,**k:i['news_check'])
    c={'captures':[{'market':'stocks','requested_symbol':'TEST'}],
       'stock_context':[{'payload':i['context'],'payload_sha256':digest(i['context'])}]}
    screen_capture(w,c,{},env={},clock=lambda:at[0])
    assert w.screen['source_ages_seconds']['TEST']['history']==0
    assert w.screen['collection_seconds']==106
    # Old reference data remains rejected: collecting history cannot freshen quotes.
    assert w.screen['blocked']==1


def test_reserved_coverage_bounded_unique_and_dynamic_sectors():
    evidence={'NVDA':{'snapshot_status':'fresh','day_change_pct':4,'turnover_usd':100000000},
              'ARM':{'snapshot_status':'fresh','day_change_pct':8,'turnover_usd':30000000},
              'XOM':{'snapshot_status':'stale','day_change_pct':20,'turnover_usd':100000000}}
    sector=leaders(evidence);assert sector==['ARM']
    pool=list(CORE)+['ARM']+['X'+str(n) for n in range(400)]
    ordered=reserve_screen(pool[13:],pool,sector,300)
    assert set(CORE)<=set(ordered) and len(ordered)==len(set(ordered))==300
    chosen,lanes=select_details(ordered,sector,NOW,39)
    assert set(CORE)<=set(chosen) and 'ARM' in chosen and len(chosen)==len(set(chosen))==39
    assert 'rotation' in lanes.values()
    # A missing/unusable symbol is not manufactured as covered.
    chosen,_=select_details(['ARM'],sector,NOW,39);assert chosen==['ARM']


def test_missed_move_reasons_do_not_invent_ai_rejection():
    m={'symbols':[{'symbol':'NVDA','day_change_pct':5,'snapshot_status':'fresh','detail_selected':False},
                  {'symbol':'AMD','day_change_pct':4,'snapshot_status':'fresh','detail_selected':True}]}
    q={'candidates':[{'candidate_id':'stocks:AMD','paper_blockers':[]}]}
    r=explain(m,q,{'candidate_id':'stocks:AMD','verdict':'NO_ACTION','blockers':['fresh_setup_no_longer_qualified']},{},now=NOW)
    rows={x['symbol']:x for x in r['rows']}
    assert rows['NVDA']['reasons']==['not_examined_in_detail']
    assert rows['AMD']['reasons']==['post_review_validation_failed']
