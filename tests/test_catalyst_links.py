from copy import deepcopy
from datetime import datetime, timedelta, timezone
from market_radar_ai.market_data.catalyst_links import discover_links, routing_report, response
from market_radar_ai.market_data.coverage_lanes import select_details, reserve_screen
NOW=datetime(2026,11,9,16,0,tzinfo=timezone.utc)
def fixtures():
    news={'NVDA':{'status':'partial','retrieved_at':NOW.isoformat(),'items':[{'evidence_id':'news-1','symbols':['NVDA'],'published_at':(NOW-timedelta(minutes=20)).isoformat(),'title':'NVIDIA announces review','url':'https://example.com/article'}]}}
    def price(n):return {'snapshot_status':'fresh','observed_at':NOW.isoformat(),'price':str(n),'prior_observation':{'observed_at':(NOW-timedelta(minutes=5)).isoformat(),'price':'100'},'turnover_usd':20000000}
    return news,{'NVDA':price(99),'AMD':price(101),'INTC':price(100.5)}
def test_attribution():
    n,p=fixtures();r=discover_links(n,p,['NVDA','AMD','INTC'],now=NOW)
    assert set(r['priority_symbols'])=={'AMD','INTC'}
    assert all(x['response']['state']=='relative_strength_observed' and not x['direct_target_news'] and x['direction']=='unknown_hypothesis_only' for x in r['rows'])
    assert not r['trade_authorized'] and r['model_calls']==0
def test_stale_future_unrelated_duplicate_news():
    n,p=fixtures()
    for delta in (-86401,1):
        v=deepcopy(n);v['NVDA']['items'][0]['published_at']=(NOW+timedelta(seconds=delta)).isoformat()
        assert not discover_links(v,p,['AMD'],now=NOW)['rows']
    v=deepcopy(n);v['NVDA']['items'][0]['symbols']=['OTHER']
    assert not discover_links(v,p,['AMD'],now=NOW)['rows']
    v=deepcopy(n);v['NVDA']['retrieved_at']=(NOW-timedelta(seconds=301)).isoformat()
    assert not discover_links(v,p,['AMD'],now=NOW)['rows']
    n['NVDA']['items']*=2;r=discover_links(n,{},['AMD'],now=NOW)
    assert len(r['rows'])==2 and r['priority_symbols']==['AMD']
    assert all(x['response']['state']=='price_evidence_unavailable' for x in r['rows'])
    assert discover_links({},p,['AMD'],now=NOW)['source_status']['NVDA']=='unavailable'
def test_no_lookahead_or_invalid_price_confirmation():
    n,prices=fixtures();pub=NOW-timedelta(minutes=20)
    for change,state in [('baseline','awaiting_post_news_baseline'),('alignment','unaligned_observation_windows'),('stale','awaiting_fresh_prices'),('nan','price_evidence_unavailable'),('fall','no_supporting_response')]:
        p=deepcopy(prices)
        if change=='baseline':p['AMD']['prior_observation']['observed_at']=(NOW-timedelta(minutes=21)).isoformat()
        if change=='alignment':p['AMD']['prior_observation']['observed_at']=(NOW-timedelta(minutes=8)).isoformat()
        if change=='stale':p['AMD']['observed_at']=(NOW-timedelta(seconds=181)).isoformat()
        if change=='nan':p['AMD']['price']='NaN'
        if change=='fall':p['AMD']['price']='98'
        assert response(p['NVDA'],p['AMD'],published=pub,now=NOW)['state']==state

def test_bounded_routing():
    assert reserve_screen(['X','Y'],['X','Y','INTC'],[],2,['INTC','UNKNOWN'])==['INTC','X']
    chosen,lanes=select_details(['X','INTC','Y'],[],NOW,2,['INTC','UNKNOWN'])
    assert len(chosen)==2 and chosen[0]=='INTC' and lanes['INTC']=='related_company_catalyst'
    assert 'INTC' not in select_details(['X','Y'],[],NOW,2,['INTC'])[0]
def test_visible_qualification_reasons():
    n,p=fixtures();r=discover_links(n,p,['AMD','INTC'],now=NOW)
    out=routing_report(r,{'symbols':[{'symbol':'AMD','detail_selected':True,'selection_reason':'selected_for_research'}]},{'candidates':[{'candidate_id':'stocks:AMD','paper_blockers':['relative_volume_below_1_5']}]})
    amd=next(x for x in out['rows'] if x['symbol']=='AMD');intel=next(x for x in out['rows'] if x['symbol']=='INTC')
    assert amd['admission_state']=='blocked' and amd['qualification_blockers']==['relative_volume_below_1_5']
    assert intel['admission_state']=='not_assessed'

def test_discovery_routes_indirect_news_before_detail_selection(monkeypatch):
    from market_radar_ai.market_data.discovery import discover
    from test_discovery import Session
    from datetime import datetime as RealDatetime
    n,p=fixtures();pool=['AMD','INTC','NVDA','X']
    class Clock:
        @staticmethod
        def now(tz):return NOW
    monkeypatch.setattr('market_radar_ai.market_data.discovery.datetime',Clock)
    # Activity parsing needs fromisoformat as well.
    Clock.fromisoformat=RealDatetime.fromisoformat
    monkeypatch.setattr('market_radar_ai.market_data.catalyst_links.fetch_seeds',lambda **kw:n)
    monkeypatch.setattr('market_radar_ai.market_data.discovery_universe.load_universe',lambda **kw:{'symbols':pool,'failures':[]})
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.discover_snapshots',lambda *a,**kw:{'failed_batches':0,'ranked_symbols':['X'],'symbol_evidence':p})
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.fetch_histories',lambda symbols,**kw:{s:s for s in symbols})
    monkeypatch.setattr('market_radar_ai.market_data.capture.capture_result',lambda *a,**kw:{'payload':{'quality_passed_at_capture':True}})
    out=discover(env={'ENABLE_BROAD_DISCOVERY':'true','SCREEN_DISCOVERY_DATA':'true','ENABLE_CATALYST_LINKS':'true','ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture'},now=NOW,session=Session(stamp=NOW.isoformat()),fallback=[])
    assert 'INTC' in out['selected_symbols']
    row=next(r for r in out['selection_manifest'] if r['symbol']=='INTC')
    assert row['detail_lane']=='related_company_catalyst' and row['related_company_catalyst']
    assert len(out['catalyst_links']['rows'])==2
