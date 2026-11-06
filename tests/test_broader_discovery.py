from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import pytest

from market_radar_ai.market_data.providers.alpaca_batch import fetch_histories, discover_snapshots
from market_radar_ai.market_data.crypto_identities import IDENTITIES, ASSETS, STABLE_ASSETS
from market_radar_ai.market_data.crypto_discovery import discover as discover_crypto
from market_radar_ai.market_data.reference_quotes import capture_quotes, validate_capture, digest
from market_radar_ai.market_data.providers.robinhood import RobinhoodEuropeCatalogue
from market_radar_ai.market_data.crypto_checks import SCOPE, assess

NOW=datetime(2026,11,6,20,tzinfo=timezone.utc)
ENV={'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture'}


class Session:
    def __init__(self, responder):self.responder=responder;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        assert kwargs['allow_redirects'] is False
        body=self.responder(url,kwargs['params'])
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,*args):yield json.dumps(body).encode()
        return Response()


def bars(count=60):
    return [dict(t=(NOW-timedelta(minutes=5*(count-i))).isoformat(),
                 o=100+i/100,h=101+i/100,l=99+i/100,c=100.5+i/100,v=200 if i>=count-5 else 100)
            for i in range(count)]


def test_three_batches_reach_300_symbols_and_isolate_missing_malformed_symbols():
    def reply(url,params):
        assert url.endswith('/stocks/bars') and params['feed']=='iex' and params['limit']==10000
        rows={s:bars() for s in params['symbols'].split(',') if s!='S3'}
        if 'S4' in rows:rows['S4'][0]['h']=1
        return {'bars':rows,'next_page_token':None}
    session=Session(reply)
    result=fetch_histories([f'S{i}' for i in range(300)],env=ENV,session=session,clock=lambda:NOW)
    assert len(session.calls)==3 and len(result)==300
    assert result['S0'].status=='ok' and len(result['S0'].candles)==60
    assert not result['S3'].candles and result['S4'].status=='error'
    assert result['S299'].status=='ok'


@pytest.mark.parametrize('fault',['pagination','unexpected_symbol','not_a_list'])
def test_incomplete_or_wrong_identity_batch_never_becomes_a_success(fault):
    data={'bars':{'S0':bars()},'next_page_token':None}
    if fault=='pagination':data['next_page_token']='not-complete'
    if fault=='unexpected_symbol':data['bars']['ALIEN']=bars()
    if fault=='not_a_list':data['bars']['S0']={}
    session=Session(lambda *a:data)
    rows=fetch_histories(['S0','S1'],env=ENV,session=session,clock=lambda:NOW)
    assert all(r.status=='error' for r in rows.values())
    assert len(session.calls)==(2 if fault=='pagination' else 1)


def test_batch_follows_pages_before_reporting_symbols_missing():
    def reply(url,params):
        if 'page_token' not in params:return {'bars':{'S0':bars()},'next_page_token':'second'}
        assert params['page_token']=='second'
        return {'bars':{'S1':bars()},'next_page_token':None}
    session=Session(reply)
    rows=fetch_histories(['S0','S1'],env=ENV,session=session,clock=lambda:NOW)
    assert len(session.calls)==2 and all(len(r.candles)==60 for r in rows.values())


def test_whole_catalogue_light_quotes_are_not_technical_checks_or_stale_success():
    fresh={'latestTrade':{'p':10,'t':NOW.isoformat()},
           'dailyBar':{'v':1000,'t':NOW.replace(hour=5).isoformat()},
           'prevDailyBar':{'c':9,'t':(NOW-timedelta(days=1)).replace(hour=5).isoformat()}}
    def reply(url,params):
        assert url.endswith('/snapshots')
        rows={s:deepcopy(fresh) for s in params['symbols'].split(',')}
        if 'S0' in rows:rows['S0']['latestTrade']['t']=(NOW-timedelta(days=1)).isoformat()
        if 'S1' in rows:rows['S1']['latestTrade']['t']=(NOW+timedelta(seconds=1)).isoformat()
        if 'S2' in rows:del rows['S2']
        return rows
    session=Session(reply)
    result=discover_snapshots([f'S{i}' for i in range(1200)],env=ENV,now=NOW,session=session,clock=lambda:NOW)
    assert len(session.calls)==3
    assert (result['requested'],result['received'],result['fresh'],result['unavailable_or_stale'])==(1200,1199,1197,3)
    assert 'technical_checked' not in result


def test_broad_stock_discovery_uses_batch_capacity_and_honest_pool_counts(monkeypatch):
    from market_radar_ai.market_data.discovery import discover
    from test_discovery import Session as ActivitySession
    pool=[f'S{i}' for i in range(5808)]
    monkeypatch.setattr('market_radar_ai.market_data.discovery_universe.load_universe',
        lambda **kw: {'symbols':pool,'failures':[]})
    def snapshots(symbols,**kw):
        assert symbols==pool
        return dict(requested=5808,received=5808,fresh=5000,unavailable_or_stale=808,
                    failed_batches=0,ranked_symbols=pool[200:5200],feed='iex',observed_at=NOW.isoformat())
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.discover_snapshots',snapshots)
    attempted=[]
    def histories(symbols,**kw):
        attempted.extend(symbols)
        return {s:s for s in symbols}
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.fetch_histories',histories)
    monkeypatch.setattr('market_radar_ai.market_data.capture.capture_result',
        lambda r,**kw:{'payload':{'quality_passed_at_capture':True}})
    r=discover(env={**ENV,'ENABLE_BROAD_DISCOVERY':'true','SCREEN_DISCOVERY_DATA':'true'},
        now=NOW,session=ActivitySession(stamp=NOW.isoformat()),fallback=['MU'])
    assert len(attempted)==len(set(attempted))==300
    assert any(s in pool[:50] for s in attempted) and any(s in pool[200:350] for s in attempted)
    assert len(r['selected_symbols'])==39  # MU/watch positions fill the 40th slot later
    assert r['coverage']['technical_checked']==300 and r['coverage']['technical_deferred']==5508
    assert r['coverage']['fresh_activity_leads']==50 and r['snapshot_coverage']['requested']==5808


def crypto_catalogue():
    return dict(source=RobinhoodEuropeCatalogue.URL,retrieved_at=NOW.isoformat(),scope=SCOPE,
                assets=[{'symbol':a,'name':n} for a,n in ASSETS.values()]+[{'symbol':'UNMAPPED','name':'Unknown identity'}])


def crypto_session(bad_pair=None):
    def reply(url,params):
        pairs=params['pair'].split(',')
        if url.endswith('AssetPairs'):
            return {'error':[],'result':{IDENTITIES[p][4]:dict(altname=p,base=IDENTITIES[p][2],
                quote='USD' if p==bad_pair else 'ZEUR',wsname=IDENTITIES[p][3],status='online') for p in pairs}}
        return {'error':[],'result':{IDENTITIES[p][4]:dict(a=['10.01','1','10'],b=['10','1','10'],
                v=['100','200'],o='9',c=['10','1']) for p in pairs}}
    return Session(reply)


def test_crypto_catalogue_expands_rotates_and_does_not_claim_account_permission():
    args=dict(fetch_catalogue=crypto_catalogue,session=crypto_session(),clock=lambda:NOW)
    a=discover_crypto(now=NOW,**args)
    b=discover_crypto(now=NOW+timedelta(minutes=5),**args)
    c=a['coverage']
    assert c['catalogue_candidates']==95 and c['identity_mapped']==94 and c['excluded_stable_assets']==2
    assert c['candidate_pool']==92 and c['quote_checked']==c['quote_usable']==92
    assert c['unmapped']==1 and c['research_selected']==30 and c['research_deferred']==62
    assert a['selected_pairs'][:15]==b['selected_pairs'][:15]
    assert a['selected_pairs'][15:]!=b['selected_pairs'][15:]
    assert not a['account_permission_verified'] and not a['trade_authorized']
    assert all(ASSETS[p][0] not in STABLE_ASSETS for p in a['selected_pairs'])


def test_crypto_unknown_identity_bad_venue_and_catalogue_outage_remain_visible():
    r=discover_crypto(now=NOW,fetch_catalogue=crypto_catalogue,session=crypto_session('ADAEUR'),clock=lambda:NOW)
    assert r['coverage']['quote_unavailable']==1
    bad=crypto_catalogue();bad['assets'][0]['name']='Different token with same ticker'
    r=discover_crypto(now=NOW,fetch_catalogue=lambda:bad,session=crypto_session(),clock=lambda:NOW)
    assert r['coverage']['unmapped']==2
    def fail():raise ValueError('do not expose me')
    r=discover_crypto(now=NOW,fetch_catalogue=fail,clock=lambda:NOW)
    assert r['status']=='unavailable' and not r['selected_pairs'] and r['coverage']['catalogue_candidates']==0
    assert 'expose' not in str(r)


def test_added_coins_reach_reference_quotes_and_broker_checks():
    pairs=['ADAEUR','AAVEEUR','AVAXEUR','XDGEUR','LINKEUR','ZROEUR']
    capture=capture_quotes(pairs,session=crypto_session(),clock=lambda:NOW)
    quotes=validate_capture(capture,now=NOW)
    assert set(quotes)==set(pairs) and all(not q['broker_executable'] for q in quotes.values())
    payload=crypto_catalogue()
    document={'crypto_catalogue':{'payload':payload,'payload_sha256':digest(payload)},'reference_quote_capture':capture}
    for pair in pairs:
        assert assess(document,symbol=pair,now=NOW)['catalogue_candidate']=='PASS'
    with pytest.raises(ValueError):validate_capture(capture,now=NOW+timedelta(seconds=30))


def test_one_bad_pair_cannot_pass_but_does_not_hide_independent_valid_quotes():
    capture=capture_quotes(['ADAEUR','AVAXEUR'],session=crypto_session('ADAEUR'),clock=lambda:NOW)
    assert capture['status']=='partial' and capture['unavailable_pairs']==['ADAEUR']
    assert set(validate_capture(capture,now=NOW))=={'AVAXEUR'}


def test_isolated_capture_failures_remain_gaps_but_whole_market_outages_fail():
    from market_radar_ai.market_data.capture import connectivity_exit_code
    failed={'market':'crypto','payload':{'provider_status':'error','candles':[]}}
    healthy={'market':'crypto','payload':{'provider_status':'ok','candles':[{}]}}
    assert connectivity_exit_code({'captures':[failed,healthy]})==0
    healthy['market']='stocks'
    assert connectivity_exit_code({'captures':[failed,healthy]})==1


def expanded_capture():
    from market_radar_ai.market_data.models import Candle,ProviderResult
    from market_radar_ai.market_data.capture import capture_markets
    from market_radar_ai.evidence.earnings_calendar import CalendarCapture,enrich as calendar_enrich
    from market_radar_ai.market_data.stock_context import fetch_context_batch,enrich as context_enrich
    stocks=[f'S{i}' for i in range(40)]
    pairs=[p for p,a in ASSETS.items() if a[0] not in STABLE_ASSETS][:30]
    def fetch(symbol,market):
        source='alpaca_iex' if market=='stocks' else 'kraken'
        return ProviderResult(provider=source,retrieved_at=NOW,candles=[Candle(symbol=symbol,
            timestamp=r['t'],interval='5m',quote_currency='USD' if market=='stocks' else 'EUR',source=source,
            open=str(r['o']),high=str(r['h']),low=str(r['l']),close=str(r['c']),volume=str(r['v'])) for r in bars()])
    doc=capture_markets(stocks,pairs,stock_fetch=lambda s:fetch(s,'stocks'),crypto_fetch=lambda s:fetch(s,'crypto'),
                        now=NOW,stock_provider='alpaca_iex',per_market_limit=40)
    def context_reply(url,params):
        rows=bars() if params['timeframe']=='5Min' else [dict(t=(NOW-timedelta(days=1)).replace(hour=5).isoformat(),o=100,h=102,l=99,c=101,v=100)]
        return {'bars':{s:rows for s in params['symbols'].split(',')},'next_page_token':None}
    doc=context_enrich(doc,batch_fetch=lambda symbols:fetch_context_batch(symbols,env=ENV,session=Session(context_reply),clock=lambda:NOW))
    doc=calendar_enrich(doc,fetch=lambda symbol:CalendarCapture(symbol=symbol,retrieved_at=NOW,
        request_from=NOW.date(),request_to=NOW.date(),status='empty',raw_payload_sha256='a'*64))
    feed={'status':'ok','scope':'SYNTHETIC_REHEARSAL','retrieved_at':NOW.isoformat(),'items':[]}
    from market_radar_ai.evidence.news import EvidenceItem
    for i in range(200):
        item=EvidenceItem(kind='news',title=f'Synthetic capacity fixture {i}',source='Fixture',
            url=f'https://example.org/fixture/{i}',published_at=NOW,retrieved_at=NOW,symbols=[])
        feed['items'].append(item.model_dump(mode='json'))
    from market_radar_ai.dashboard.api_budget import summarize
    from market_radar_ai.agents.github_budget import initial_state
    doc['api_budget']=summarize(initial_state(),now=NOW)
    from market_radar_ai.dashboard.discovery_coverage import build_coverage
    stock_discovery={'coverage':dict(catalogue_candidates=5808,candidate_pool=5808,
        technical_checked=300,technical_usable=280,technical_unavailable=20,technical_deferred=5508,
        research_selected=40,research_deferred=5768),'fallback_used':False,
        'snapshot_coverage':dict(requested=5808,fresh=5000,unavailable_or_stale=808)}
    crypto=discover_crypto(now=NOW,fetch_catalogue=crypto_catalogue,session=crypto_session(),clock=lambda:NOW)
    doc['discovery_coverage']=build_coverage(stock_discovery,crypto,doc,now=NOW)
    return doc,feed


def test_maximum_collection_passes_full_offline_pipeline_under_ingest_limit():
    from market_radar_ai.dashboard.export import build_snapshot
    from market_radar_ai.market_data.readiness import readiness
    from market_radar_ai.agents.qualification import qualify
    from market_radar_ai.agents.paper_verdict import build_packets
    from market_radar_ai.agents.context_packages import build_context_packages
    doc,feed=expanded_capture()
    snapshot=build_snapshot(doc,now=NOW,evidence=feed)
    assert len(snapshot['charts']['series'])==70
    assert len(snapshot['research_briefing']['rows'])==40 and len(snapshot['evidence']['items'])==200
    assert len(json.dumps(snapshot).encode())<2_000_000 and len(json.dumps(doc,indent=2).encode())<4_000_000
    assert readiness(doc,feed,now=NOW)['capture_expiry_replay']['all_original_captures_rejected']
    assert len(build_context_packages(doc,feed,now=NOW)['packages'])==40
    result=qualify(doc,feed,now=NOW)
    assert len(result['candidates'])==70
    assert not build_packets(doc,feed,now=NOW)['packets']  # missing broker/news evidence still blocks
    assert not snapshot['live_orders_enabled']


@pytest.mark.parametrize('fault',['negative','bool','mismatch','future','unknown_field','selected'])
def test_discovery_contract_rejects_wrong_counts_and_future_timestamps(fault):
    from market_radar_ai.dashboard.export import build_snapshot
    doc,feed=expanded_capture();data=doc['discovery_coverage']
    if fault=='negative':data['stocks']['quote_unavailable']=-1
    if fault=='bool':data['stocks']['quote_usable']=True
    if fault=='mismatch':data['stocks']['technical_deferred']+=1
    if fault=='future':data['observed_at']=(NOW+timedelta(microseconds=1)).isoformat()
    if fault=='unknown_field':data['credential']='forbidden'
    if fault=='selected':data['stocks']['detail_selected']-=1
    with pytest.raises(ValueError):build_snapshot(doc,now=NOW,evidence=feed)
