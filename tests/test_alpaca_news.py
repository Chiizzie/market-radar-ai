from datetime import datetime, timedelta
import json
import pytest
from market_radar_ai.evidence.alpaca_news import fetch_alpaca_news, parse_alpaca_news
from market_radar_ai.evidence.scanner_feed import collect
from market_radar_ai.agents.context_packages import build_context_packages
from test_stock_context import NOW, document


def payload():
    return {'news':[{'id':123, 'headline':'Company update', 'source':'benzinga',
        'url':'https://www.benzinga.com/news/company-update', 'symbols':['MSFT'],
        'created_at':(NOW-timedelta(hours=1)).isoformat(),
        'updated_at':(NOW-timedelta(minutes=20)).isoformat()}], 'next_page_token':None}


def parse(data):
    return parse_alpaca_news(data,symbol='MSFT',now=NOW,start=NOW-timedelta(days=7))


def test_explicit_tags_reach_context_with_original_publisher_and_time():
    feed=parse(payload())
    result=collect(company_fetch=lambda _:feed,company_symbols=['MSFT'],
        public_fetch=lambda **_: {'status':'error'},clock=lambda:NOW)
    package=build_context_packages(document(),result,now=NOW)['packages'][0]['package']
    assert len(package['news_source_ids'])==1
    item=feed['items'][0]
    assert item['symbols']==['MSFT'] and item['source']=='benzinga'
    assert datetime.fromisoformat(item['published_at'])==datetime.fromisoformat(payload()['news'][0]['created_at'])
    assert not feed['coverage_complete'] and not package['trade_authorized']
    assert 'independent_catalyst_confirmation_missing' in package['missing_evidence']


@pytest.mark.parametrize('field,value',[
    ('symbols',[]),('symbols',['AAPL']),('symbols','MSFT'),('symbols',['MSFT','bad/tag']),
    ('created_at',(NOW-timedelta(days=8)).isoformat()),
    ('updated_at',(NOW+timedelta(seconds=1)).isoformat()),
    ('created_at','2026-11-04T12:00:00'),('url','http://example.com/story'),
])
def test_reject_unrelated_invalid_or_out_of_window_articles(field,value):
    data=payload();data['news'][0][field]=value
    result=parse(data)
    assert not result['items'] and len(result['rejected'])==1


def test_deduplication_pagination_and_empty_are_partial():
    data=payload();data['news']*=2;data['next_page_token']='opaque'
    r=parse(data)
    assert len(r['items'])==1 and r['more_available'] and r['status']=='partial'
    assert parse({'news':[]})['status']=='partial'


class Session:
    def __init__(self,status=200,body=None):self.status=status;self.body=body;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs));outer=self
        class Response:
            status_code=outer.status
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,*args):
                yield outer.body if outer.body is not None else json.dumps(payload()).encode()
        return Response()


def fetch(session,env=None):
    return fetch_alpaca_news('MSFT',session=session,
        env={'ALPACA_API_KEY':'test-private','ALPACA_API_SECRET':'test-secret'} if env is None else env,
        clock=lambda:NOW)


def test_fixed_bounded_read_only_request_and_no_credentials_in_result():
    session=Session();r=fetch(session)
    assert len(session.calls)==1 and r['items'] and len(r['raw_payload_sha256'])==64
    url,k=session.calls[0]
    assert url=='https://data.alpaca.markets/v1beta1/news'
    assert not k['allow_redirects'] and k['stream'] and k['timeout']==(5,15)
    assert k['params']['limit']==10 and k['params']['include_content']=='false'
    assert 'test-private' not in str(r) and 'test-secret' not in str(r)


@pytest.mark.parametrize('status,reason',[(403,'access_denied'),(429,'rate_limited'),(302,'provider_http_error')])
def test_access_and_rate_failures_remain_visible(status,reason):
    r=fetch(Session(status));assert r['status']=='error' and r['reason']==reason


def test_missing_credentials_and_invalid_symbol_make_no_requests():
    s=Session();assert fetch(s,env={})['status']=='not_configured' and not s.calls
    with pytest.raises(ValueError):fetch_alpaca_news('../MSFT',session=s,env={})
    assert not s.calls


@pytest.mark.parametrize('body',[b'x'*1_000_001,b'{broken',b'{"news":null}'])
def test_oversized_and_malformed_response_fail_closed(body):
    assert fetch(Session(body=body))['status']=='error'
