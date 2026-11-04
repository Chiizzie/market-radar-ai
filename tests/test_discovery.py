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
    assert len(all_)==100 and len(a)==len(set(a))==8
    assert a[:4]==b[:4] and a[4:]!=b[4:]
def test_discovery_deduplicates_bounds_and_accounts():
    r=discover(env={'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y'},now=NOW,fallback=['AAPL'],session=Session())
    assert r['discovered_count']==50 and len(r['selected_symbols'])==8
    assert len(r['deferred_symbols'])==42 and not r['fallback_used']
    assert not r['trade_authorized']
def test_stale_bad_or_missing_credentials_report_fallback():
    for session,env in [(Session((NOW-timedelta(days=1)).isoformat()),{'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y'}),(Session(bad=True),{'ALPACA_API_KEY':'x','ALPACA_API_SECRET':'y'}),(Session(),{})]:
        r=discover(env=env,now=NOW,fallback=['AAPL'],session=session)
        assert r['fallback_used'] and r['discovered_count']==0 and r['selected_symbols']==['AAPL']
