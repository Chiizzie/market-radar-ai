from datetime import datetime, timezone, timedelta
import json
from market_radar_ai.market_data.discovery import discover, select
NOW=datetime(2026,11,4,16,tzinfo=timezone.utc)
class Session:
    def __init__(self,stamp=None,bad=False):self.stamp=stamp or NOW.isoformat();self.bad=bad
    def get(self,url,**kw):
        assert kw['allow_redirects'] is False
        rows=[{'symbol':('BAD/URL' if self.bad else 'S'+str(i))} for i in range(50)]
        body={'last_updated':self.stamp,'most_actives':rows,'gainers':rows,'losers':rows}
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def iter_content(self,n):yield json.dumps(body).encode()
        return Response()
def test_selection_rotates_deferred_without_duplicates():
    groups=[['S'+str(i) for i in range(100)]]
    all_,a=select(groups,NOW);_,b=select(groups,NOW+timedelta(minutes=15))
    assert len(all_)==100 and len(a)==len(set(a))==19
    assert a[:9]==b[:9] and a[9:]!=b[9:]
def test_discovery_deduplicates_bounds_and_accounts():
    r=discover(env={'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y'},now=NOW,fallback=['AAPL'],session=Session())
    assert r['discovered_count']==50 and len(r['selected_symbols'])==19
    assert len(r['deferred_symbols'])==31 and not r['fallback_used']
    assert not r['trade_authorized']
def test_stale_bad_or_missing_credentials_report_fallback():
    for session,env in [(Session((NOW-timedelta(days=1)).isoformat()),{'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y'}),(Session(bad=True),{'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y'}),(Session(),{})]:
        r=discover(env=env,now=NOW,fallback=['AAPL'],session=session)
        assert r['fallback_used'] and r['discovered_count']==0 and r['selected_symbols']==['AAPL']


def test_catalogue_and_quality_screen_filters_before_selection(monkeypatch):
    from types import SimpleNamespace
    from market_radar_ai.market_data.models import ProviderResult
    monkeypatch.setattr('market_radar_ai.market_data.providers.catalogues.Trading212Catalogue.fetch',lambda self:[SimpleNamespace(ticker='S'+str(i)+'_US_EQ',type='STOCK',currencyCode='USD') for i in range(15)])
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca.AlpacaIexProvider.fetch_history',lambda self,s:s)
    monkeypatch.setattr('market_radar_ai.market_data.capture.capture_result',lambda r,**k:{'payload':{'quality_passed_at_capture':r!='S0'}})
    r=discover(env={'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y','SCREEN_DISCOVERY_DATA':'true'},now=NOW,fallback=['AAPL'],session=Session())
    assert 'S0' not in r['selected_symbols'] and 'S0' in r['screening']['rejected']
    assert len(r['selected_symbols'])==14 and not r['fallback_used']
    assert not r['screening']['account_permission_verified']


def test_broad_screen_checks_every_pool_member_and_rotates_enrichment(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('market_radar_ai.market_data.providers.catalogues.Trading212Catalogue.fetch',lambda self:[SimpleNamespace(ticker='S'+str(i)+'_US_EQ',type='STOCK',currencyCode='USD') for i in range(50)])
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca.AlpacaIexProvider.fetch_history',lambda self,s:s)
    monkeypatch.setattr('market_radar_ai.market_data.capture.capture_result',lambda r,**k:{'payload':{'quality_passed_at_capture':True}})
    env={'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y','SCREEN_DISCOVERY_DATA':'true'}
    a=discover(env=env,now=NOW,fallback=['MU'],session=Session())
    b=discover(env=env,now=NOW+timedelta(minutes=5),fallback=['MU'],session=Session())
    assert a['screening']['checked']==b['screening']['checked']==50
    assert not a['screening']['not_checked']
    assert len(a['selected_symbols'])==19
    assert len(a['screening']['deferred_after_screen'])==31
    assert a['selected_symbols'][:9]==b['selected_symbols'][:9]
    assert a['selected_symbols'][9:]!=b['selected_symbols'][9:]
    assert not a['trade_authorized']
