from datetime import datetime,timezone
import pytest
from market_radar_ai.evidence.public_feed import parse_feed
NOW=datetime(2026,11,2,15,tzinfo=timezone.utc)
ITEM='<item><title>Policy announcement</title><link>https://www.federalreserve.gov/newsevents/pressreleases/example.htm</link><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item>'


def feed(items):return ('<rss><channel>'+items+'</channel></rss>').encode()


def test_primary_feed_has_no_invented_symbols_or_event_time():
    r=parse_feed(feed(ITEM+ITEM),now=NOW)
    assert len(r['items'])==1
    assert r['items'][0]['symbols']==[]
    assert r['items'][0]['event_at'] is None
    assert r['rejected'][0]['reason']=='duplicate_url'
    assert not r['trade_authorized']


@pytest.mark.parametrize('body',[b'<!DOCTYPE rss><rss><channel/></rss>',b'<html/>',b'<rss>\x00</rss>'])
def test_unsafe_or_wrong_document_rejected(body):
    with pytest.raises(ValueError):parse_feed(body,now=NOW)


def test_nonpublisher_and_future_items_rejected():
    assert not parse_feed(feed(ITEM.replace('www.federalreserve.gov','example.com')),now=NOW)['items']
    assert not parse_feed(feed(ITEM.replace('14:00:00','16:00:00')),now=NOW)['items']


def test_issuer_registry_changes_source_without_inventing_relevance():
    body=feed(ITEM.replace('www.federalreserve.gov','news.microsoft.com'))
    result=parse_feed(body,now=NOW,publisher='Microsoft Source',hosts=('news.microsoft.com',),
                      provider='microsoft_source_rss',scope='SINGLE_ISSUER_EDITORIAL_NEWS')
    assert result['items'][0]['source']=='Microsoft Source'
    assert result['scope']=='SINGLE_ISSUER_EDITORIAL_NEWS'
    assert not result['items'][0]['symbols']


class Response:
    def __init__(self, status=200, body=b'<html/>'):
        self.status_code, self.body = status, body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size): yield self.body


class Session:
    def __init__(self, response): self.response = response
    def get(self, url, **kwargs):
        assert kwargs['allow_redirects'] is False
        return self.response


@pytest.mark.parametrize('status,body,reason', [
    (301,b'', 'redirect_not_followed'),
    (403,b'sensitive upstream body', 'http_error'),
    (200,b'<html/>', 'invalid_feed'),
    (200,b'x'*2_000_001, 'response_too_large'),
])
def test_feed_failure_diagnostics_are_bounded(status, body, reason):
    from market_radar_ai.evidence.public_feed import fetch_feed
    result = fetch_feed(Session(Response(status, body)), issuer=True)
    assert result['status'] == 'error'
    assert result['reason'] == reason
    assert result['http_status'] == status
    assert 'sensitive' not in str(result)
    assert result['items'] == []


def test_nvidia_registry_assigns_publisher_symbol_only_to_allowlisted_items():
    from market_radar_ai.evidence.public_feed import fetch_feed
    from datetime import datetime
    now = datetime.now(timezone.utc)
    article = ITEM.replace('www.federalreserve.gov', 'blogs.nvidia.com').replace('Mon, 02 Nov 2026 14:00:00 GMT', now.strftime('%a, %d %b %Y %H:%M:%S GMT'))
    evil = article.replace('blogs.nvidia.com', 'blogs.nvidia.com.attacker.example')
    result = fetch_feed(Session(Response(200, feed(article+evil))), source='nvidia')
    assert len(result['items']) == 1
    assert result['items'][0]['symbols'] == ['NVDA']
    assert result['items'][0]['verification'] == 'provider_reported'
    assert result['rejected'][0]['reason'] == 'invalid_item'
    assert not result['trade_authorized']


def test_source_selector_rejects_arbitrary_endpoints():
    from market_radar_ai.evidence.public_feed import fetch_feed
    with pytest.raises(ValueError): fetch_feed(source='https://example.com')
    with pytest.raises(ValueError): fetch_feed(issuer=True, source='nvidia')


def test_transport_retry_is_bounded_and_records_recovery(monkeypatch):
    from market_radar_ai.evidence import public_feed as module
    results=iter([{'status':'error','reason':'transport_error'}, {'status':'ok','items':[]}])
    monkeypatch.setattr(module,'_fetch_feed_once',lambda *a,**kw:next(results))
    result=module.fetch_feed(source='nvidia')
    assert result['status']=='ok' and len(result['fetch_attempts'])==2


def test_http_error_never_retried(monkeypatch):
    from market_radar_ai.evidence import public_feed as module
    calls=[]
    def fetch(*a,**kw):
        calls.append(1)
        return {'status':'error','reason':'http_error','http_status':429}
    monkeypatch.setattr(module,'_fetch_feed_once',fetch)
    assert module.fetch_feed()['status']=='error'
    assert len(calls)==1


def test_transport_failure_stops_after_two_attempts(monkeypatch):
    from market_radar_ai.evidence import public_feed as module
    calls=[]
    def fetch(*a,**kw):
        calls.append(1)
        return {'status':'error','reason':'transport_error'}
    monkeypatch.setattr(module,'_fetch_feed_once',fetch)
    assert module.fetch_feed()['status']=='error'
    assert len(calls)==2


def test_feed_connection_budget_allows_slow_handshake():
    from market_radar_ai.evidence.public_feed import fetch_feed
    class SlowSession:
        def get(self,url,**kwargs):
            assert kwargs['timeout']==(15,20)
            assert kwargs['allow_redirects'] is False
            assert kwargs['stream'] is True
            return Response(200,feed(''))
    assert fetch_feed(SlowSession(),source='nvidia')['status']=='ok'
