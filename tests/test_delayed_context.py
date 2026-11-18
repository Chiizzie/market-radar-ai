from datetime import timedelta
from market_radar_ai.market_data.delayed_context import fetch,enrich_delayed
from market_radar_ai.agents.early_screening import screen
from test_stock_context import Session,NOW,document

class DelayedSession(Session):
    def get(self,url,**kw):
        import json
        assert kw['params']['feed']=='sip'
        from datetime import datetime
        assert NOW-datetime.fromisoformat(kw['params']['end'])>=timedelta(minutes=15)
        assert not kw['allow_redirects']
        bar={'t':(NOW-timedelta(minutes=25)).isoformat(),'o':100,'h':102,'l':99,'c':101,'v':100}
        data={'symbol':'MSFT','bars':[bar],'next_page_token':None}
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def iter_content(self,*a):yield json.dumps(data).encode()
        return Response()


def test_delayed_context_is_separate_labelled_and_cannot_become_live_evidence():
    record=fetch('MSFT',env={'ALPACA_API_KEY':'fake','ALPACA_API_SECRET':'fake'},session=DelayedSession(),clock=lambda:NOW)
    doc=document();doc['stock_context'][0]['payload_sha256']='bad'
    doc=enrich_delayed(doc,fetcher=lambda _:record,now=NOW)
    r=screen(doc,now=NOW)['candidates'][0]
    assert r['source']=='alpaca_sip_delayed' and r['data_delay_seconds']==900
    assert not r['trade_authorized']
    assert doc['stock_context'][0]['payload_sha256']=='bad'
    assert screen(doc,now=NOW+timedelta(minutes=16))['candidates'][0]['state']=='UNAVAILABLE'


def test_regular_session_never_requests_delayed_fallback():
    def fail(_):raise AssertionError('unexpected fetch')
    assert 'delayed_stock_context' not in enrich_delayed(document(),fetcher=fail,now=NOW.replace(hour=16))
