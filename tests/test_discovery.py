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


def catalogue(monkeypatch, count=500):
    from types import SimpleNamespace
    monkeypatch.setattr('market_radar_ai.market_data.providers.catalogues.Trading212Catalogue.fetch',
                        lambda self: [SimpleNamespace(ticker=f'S{i}_US_EQ', type='STOCK',
                                                      currencyCode='USD') for i in range(count)])


def test_stale_premarket_movers_still_rotate_persisted_catalogue(tmp_path, monkeypatch):
    catalogue(monkeypatch)
    def no_history(*args, **kwargs):
        raise AssertionError('Premarket rotation must not fetch regular-session history')
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca.AlpacaIexProvider.fetch_history', no_history)
    pre = NOW.replace(hour=12)
    env = {'ALPACA_API_KEY': 'x', 'ALPACA_API_SECRET': 'y', 'SCREEN_DISCOVERY_DATA': 'true'}
    kwargs = dict(env=env, fallback=['AAPL'], session=Session((pre-timedelta(days=1)).isoformat()),
                  universe_cache_path=tmp_path/'universe.json')
    first = discover(now=pre, **kwargs)
    # A different collector instance can reuse the first one's on-disk universe.
    monkeypatch.setattr('market_radar_ai.market_data.providers.catalogues.Trading212Catalogue.fetch', no_history)
    second = discover(now=pre+timedelta(minutes=5), **kwargs)
    assert first['universe']['cache_status'] == 'refreshed'
    assert second['universe']['cache_status'] == 'reused'
    assert first['universe']['retrieved_at'] == second['universe']['retrieved_at']
    assert not first['fallback_used'] and first['discovered_count'] == 0
    assert len(first['selected_symbols']) == 19
    assert set(first['selected_symbols']).isdisjoint(second['selected_symbols'])
    assert first['coverage'] == {
        'catalogue_candidates': 500, 'fresh_activity_leads': 0, 'candidate_pool': 500,
        'technical_checked': 0, 'technical_usable': 0, 'technical_unavailable': 0,
        'technical_deferred': 500, 'research_selected': 19, 'research_deferred': 481,
    }
    assert len(first['screening']['not_checked']) == 500
    assert first['screening']['usable_count'] == 0
    assert first['broker_eligibility'] == 'unknown' and not first['trade_authorized']


def test_regular_screen_is_bounded_and_provider_failure_is_unavailable(monkeypatch):
    catalogue(monkeypatch)
    checked = []
    def history(self, symbol):
        checked.append(symbol)
        if symbol == 'S0':
            raise RuntimeError('secret provider error must never reach discovery')
        return symbol
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca.AlpacaIexProvider.fetch_history', history)
    monkeypatch.setattr('market_radar_ai.market_data.capture.capture_result',
                        lambda r, **k: {'payload': {'quality_passed_at_capture': True}})
    result = discover(env={'ALPACA_API_KEY': 'x', 'ALPACA_API_SECRET': 'y',
                           'SCREEN_DISCOVERY_DATA': 'true'}, now=NOW,
                      fallback=['AAPL'], session=Session())
    assert len(checked) == len(set(checked)) == 100
    assert set(f'S{i}' for i in range(50)) <= set(checked)
    assert any(int(s[1:]) >= 50 for s in checked)
    assert result['coverage']['technical_checked'] == 100
    assert result['coverage']['technical_unavailable'] == 1
    assert result['coverage']['technical_usable'] == 99
    assert result['coverage']['technical_deferred'] == 400
    assert len(result['selected_symbols']) == 19 and 'S0' not in result['selected_symbols']
    assert 'secret' not in json.dumps(result)


def test_catalogue_rotation_eventually_reaches_every_symbol_without_activity():
    from market_radar_ai.market_data.discovery import catalogue_selection
    pool = [f'S{i}' for i in range(503)]
    seen = set()
    for step in range(27):
        chosen = catalogue_selection([], pool, NOW+timedelta(minutes=5*step), limit=19)
        assert len(chosen) == len(set(chosen)) == 19
        seen.update(chosen)
    assert seen == set(pool)
