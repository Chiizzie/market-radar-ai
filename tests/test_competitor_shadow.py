from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from test_method_shadow import fixture, NOW
from test_comparison_live import MemoryEvents
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.competitor_shadow import scenario, PROTOCOL_ID
from market_radar_ai.agents.method_shadow import MethodShadow
from market_radar_ai.market_data.catalyst_links import RELATIONSHIP_SOURCE

def inputs():
    i=fixture();i['symbol']='AMD';i['context']['symbol']='AMD';i['news_check']['query_symbol']='AMD'
    for c in i['candles']+i['daily']:c['symbol']='AMD'
    # Wider recent range makes a cost-inclusive 2R projection feasible.
    for c in i['candles'][-3:]:c['low']='98';c['volume']='100000'
    p=i['reference_checks']['payload'];p['symbols']=['AMD']
    p['catalogue_candidates']={'AMD':[{'ticker':'AMD_US_EQ'}]}
    p['quotes']['quotes']={'AMD':p['quotes']['quotes']['TEST']}
    i['reference_checks']['payload_sha256']=digest(p)
    def price(n):return {'snapshot_status':'fresh','observed_at':NOW.isoformat(),'price':str(n),'prior_observation':{'observed_at':(NOW-timedelta(minutes=5)).isoformat(),'price':'100'},'turnover_usd':20000000}
    i['competitor_evidence']={'links':[{'symbol':'AMD','source_symbol':'NVDA','relationship_source':RELATIONSHIP_SOURCE,'direct_target_news':False,'headline':'NVIDIA announces review','evidence_id':'fixture-news','news_url':'https://example.com/news','published_at':(NOW-timedelta(minutes=20)).isoformat(),'news_retrieved_at':NOW.isoformat()}], 'snapshots':{'NVDA':price(99),'AMD':price(101)}}
    return i

def test_independent_risk_costs_and_protocol():
    s=scenario(inputs(),now=NOW);assert not s['blockers'],s['blockers']
    p=s['plan'];loss=(Decimal(p['entry_eur'])-Decimal(p['stop_eur']))*Decimal(p['quantity'])+Decimal(p['assumed_round_trip_cost_eur'])
    assert 0<loss<=20 and Decimal(p['entry_eur'])*Decimal(p['quantity'])<=500
    assert s['protocol_id']==PROTOCOL_ID and not s['trade_authorized']

def test_fail_closed_news_price_chart_and_entry():
    for fault in ('missing','stale_news','future_news','unrelated','source','prices','future_bar','gap','passed','spread','fx'):
        i=inputs()
        if fault=='missing':del i['competitor_evidence']
        if fault=='stale_news':i['competitor_evidence']['links'][0]['news_retrieved_at']=(NOW-timedelta(seconds=901)).isoformat()
        if fault=='future_news':i['competitor_evidence']['links'][0]['published_at']=(NOW+timedelta(seconds=1)).isoformat()
        if fault=='unrelated':i['competitor_evidence']['links'][0]['source_symbol']='OTHER'
        if fault=='source':i['competitor_evidence']['links'][0]['relationship_source']='https://example.com'
        if fault=='prices':i['competitor_evidence']['snapshots']['AMD']['price']='99'
        if fault=='future_bar':i['candles'][-1]['timestamp']=NOW.isoformat()
        if fault=='gap':i['candles'][-2]['timestamp']=i['candles'][-1]['timestamp']
        p=i['reference_checks']['payload']
        if fault=='passed':p['quotes']['quotes']['AMD']['ap']=102
        if fault=='spread':p['quotes']['quotes']['AMD']['bp']=99
        if fault=='fx':p['fx']['observed_at']=(NOW-timedelta(days=1)).isoformat()
        i['reference_checks']['payload_sha256']=digest(p)
        assert scenario(i,now=NOW)['blockers'],fault

def test_durable_fill_close_restore_and_partition(tmp_path):
    i=inputs();t=[NOW];events=MemoryEvents();s=scenario(i,now=NOW);price=[s['plan']['entry_eur']]
    obs=SimpleNamespace(fetch=lambda ds:([{'packet_id':d['packet_id'],'source':'alpaca_iex:'+'a'*64,'quote':{'observed_at':t[0].isoformat(),'bid':price[0],'ask':price[0]}} for d in ds],[]))
    w=MethodShadow(tmp_path/'first',client=events,observer=obs,clock=lambda:t[0],competitor=True)
    assert w.enrol(i,now=t[0])==[]
    t[0]+=timedelta(seconds=2);w.poll();assert w.outcomes(t[0])[0]['state']=='open_simulation'
    price[0]=s['plan']['target_eur'];t[0]+=timedelta(seconds=2);w.poll();assert w.outcomes(t[0])[0]['state']=='closed'
    w.close();assert (tmp_path/'first/competitor-shadow-report.json').exists()
    restored=MethodShadow(tmp_path/'restore',client=events,clock=lambda:t[0],competitor=True);restored.sync()
    assert restored.outcomes(t[0])==w.outcomes(t[0])
    assert restored.enrol(i,now=t[0])==['already_enrolled_this_session']
    baseline=MethodShadow(tmp_path/'baseline',client=events,clock=lambda:t[0]);baseline.sync();assert not baseline.cohorts
    assert not any(e['kind']=='method_report' for e in events.events)

def test_screen_refreshes_competitor_prices_and_enrols_separate_worker(monkeypatch,tmp_path):
    from market_radar_ai.agents.method_shadow import screen_capture
    from market_radar_ai.market_data.models import Candle
    i=inputs();events=MemoryEvents();order=[]
    w=MethodShadow(tmp_path/'base',client=events,clock=lambda:NOW)
    c=MethodShadow(tmp_path/'competitor',client=events,clock=lambda:NOW,competitor=True)
    def histories(*a,**kw):
        order.append('bars');return {'AMD':SimpleNamespace(status='ok',retrieved_at=NOW,candles=[Candle.model_validate(x) for x in i['candles']])}
    def snapshots(symbols,**kw):
        order.append('prices');assert set(symbols)=={'NVDA','AMD'}
        assert kw['prior_snapshots']['AMD']['price']=='100'
        return {'symbol_evidence':i['competitor_evidence']['snapshots']}
    def collect(*a,before_quotes,**kw):
        before_quotes();order.append('quotes');return i['reference_checks']
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.fetch_histories',histories)
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.discover_snapshots',snapshots)
    monkeypatch.setattr('market_radar_ai.market_data.stock_checks.collect',collect)
    monkeypatch.setattr('market_radar_ai.agents.chart_news.checked_source',lambda *a,**kw:i['news_check'])
    capture={'captures':[{'market':'stocks','requested_symbol':'AMD'}],'stock_context':[{'payload':i['context'],'payload_sha256':digest(i['context'])}]}
    screen_capture(w,capture,{},env={},clock=lambda:NOW,competitor=c,
        discovery={'catalyst_links':{'rows':i['competitor_evidence']['links']}},
        manifest={'symbols':[{'symbol':'AMD','snapshot_status':'fresh','price':'100','observed_at':(NOW-timedelta(minutes=5)).isoformat()}]})
    assert order==['bars','prices','quotes'] and c.screen['enrolled']==1
