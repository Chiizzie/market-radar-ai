from copy import deepcopy
from datetime import timedelta
import json
import pytest
from test_capture_shortlist import capture,NOW
from market_radar_ai.evidence.crypto_feed import parse_crypto_feed
from market_radar_ai.evidence.scanner_feed import collect
from market_radar_ai.market_data.reference_quotes import validate_capture, digest, capture_quotes
from market_radar_ai.agents.candidate_packages import build_packages
from market_radar_ai.agents.candidate_review import reproduce
from test_scanner_news import feed as stock_feed


def news(tags='<category>XRP</category>', title='A Bitcoin headline is not an asset tag'):
    from email.utils import format_datetime
    return parse_crypto_feed(f'<rss><channel><item><title>{title}</title><link>https://www.coindesk.com/markets/test</link><pubDate>{format_datetime(NOW)}</pubDate>{tags}</item></channel></rss>'.encode(),now=NOW)


def reference():
    payload={'asset_pairs':{'error':[],'result':{'XXRPZEUR':{'altname':'XRPEUR','base':'XXRP',
        'quote':'ZEUR','wsname':'XRP/EUR','status':'online'}}},
        'tickers':{'error':[],'result':{'XXRPZEUR':{'a':['1.001','1','200.0'],'b':['1.000','1','300.0']}}}}
    return {'schema_version':'kraken-reference-capture-v1','requested_pairs':['XRPEUR'],
        'request_started_at':(NOW-timedelta(seconds=1)).isoformat(),'retrieved_at':NOW.isoformat(),
        'status':'ok','trade_authorized':False,'payload':payload,'payload_sha256':digest(payload)}


def test_crypto_categories_are_exact_namespace_links_not_headline_guesses():
    f=news()
    assert f['items'][0]['symbols']==['COINDESK:XRP']
    assert not news('')['items'][0]['symbols']
    assert news('<category>Bitcoin Cash</category><category>Ripple</category>')['items'][0]['symbols']==['COINDESK:BCH']
    assert news('<category>Bitcoin</category>')['items'][0]['symbols']==['COINDESK:BTC']
    assert news('<category>Bitcoin News</category><category>Ethereum News</category>')['items'][0]['symbols']==['COINDESK:BTC','COINDESK:ETH']
    assert f['status']=='partial' and not f['coverage_complete']


def test_crypto_feed_rejects_foreign_publisher_and_xml_entities():
    from email.utils import format_datetime
    body=f'<rss><channel><item><title>T</title><link>https://evil.example/test</link><pubDate>{format_datetime(NOW)}</pubDate><category>XRP</category></item></channel></rss>'
    assert parse_crypto_feed(body.encode(),now=NOW)['items']==[]
    with pytest.raises(ValueError):parse_crypto_feed(b'<!DOCTYPE rss><rss><channel/></rss>',now=NOW)


def test_combined_collector_keeps_crypto_failure_visible():
    def fail():raise RuntimeError('secret')
    def current(s):
        f=stock_feed(s);f['retrieved_at']=NOW.isoformat()
        for row in f['items']:
            row['published_at']=row['retrieved_at']=NOW.isoformat()
        return f
    f=collect(company_fetch=current, public_fetch=lambda **kw:current(kw['source']),
        crypto_fetch=fail,clock=lambda:NOW)
    assert f['status']=='partial' and f['sources'][-1]['status']=='error'
    assert 'secret' not in str(f)


def test_quote_identity_spread_and_local_time_are_explicit():
    r=validate_capture(reference(),now=NOW)['XRPEUR']
    assert r['bid']=='1.000' and r['ask']=='1.001' and r['quote_currency']=='EUR'
    assert r['exchange_timestamp'] is None and r['timestamp_basis']=='LOCAL_RECEIPT_ONLY'
    assert r['broker_executable'] is False
    assert r['expires_at']==(NOW+timedelta(seconds=30)).isoformat()


@pytest.mark.parametrize('mutation',['wrong_pair','offline','crossed','zero','nan','numeric','bad_hash','ambiguous','wrong_base','empty_ask','short_bid','naive_time'])
def test_invalid_reference_is_rejected(mutation):
    d=reference();p=d['payload'];m=p['asset_pairs']['result']['XXRPZEUR'];t=p['tickers']['result']['XXRPZEUR']
    if mutation=='wrong_pair':m['quote']='ZUSD'
    if mutation=='offline':m['status']='cancel_only'
    if mutation=='crossed':t['b'][0]='2'
    if mutation=='zero':t['a'][2]='0'
    if mutation=='nan':t['b'][0]='NaN'
    if mutation=='numeric':t['b'][0]=1.0
    if mutation=='wrong_base':m['base']='SOL'
    if mutation=='empty_ask':t['a']=[]
    if mutation=='short_bid':t['b']=['1']
    if mutation=='naive_time':d['retrieved_at']=NOW.replace(tzinfo=None).isoformat()
    if mutation=='ambiguous':p['asset_pairs']['result']['other']=deepcopy(m)
    d['payload_sha256']=digest(p)
    if mutation=='bad_hash':d['payload_sha256']='0'*64
    with pytest.raises((ValueError,ArithmeticError)):validate_capture(d,now=NOW)


@pytest.mark.parametrize('seconds',[-1,30,60])
def test_quote_cannot_outlive_receipt_ttl_or_use_future_time(seconds):
    with pytest.raises(ValueError):validate_capture(reference(),now=NOW+timedelta(seconds=seconds))


def test_enrichment_reaches_review_package_without_clearing_execution_gaps():
    d=capture(('XRPEUR',));d['reference_quote_capture']=reference();f=news()
    record=build_packages(d,f,now=NOW)['packages'][0]
    b=record['package'];source=b['sources'][b['source_ids'][0]]
    assert source['reference_quote']['broker_executable'] is False
    assert len(b['news_source_ids'])==1 and b['expires_at']==source['reference_quote']['expires_at']
    assert 'crypto_news_identity_adapter_missing' not in b['missing_evidence']
    for gap in ('broker_account_eligibility_unverified','executable_quotes_and_costs_missing',
                'independent_catalyst_confirmation_missing','reference_venue_is_not_execution_broker'):
        assert gap in b['missing_evidence']
    assert not b['trade_authorized'] and b['plan'] is None
    restored=json.loads(json.dumps(record))
    assert reproduce(restored,json.loads(json.dumps(d)),f,now=NOW)['candidate_id']=='crypto:XRPEUR'


def test_untrusted_plain_ticker_or_publisher_does_not_link_crypto_news():
    d=capture(('XRPEUR',));f=news();f['items'][0]['source']='Other Publisher'
    assert not build_packages(d,f,now=NOW)['packages'][0]['package']['news_source_ids']
    f=news();f['items'][0]['symbols']=['XRPEUR','XRP']
    assert not build_packages(d,f,now=NOW)['packages'][0]['package']['news_source_ids']


def test_stale_quote_leaves_candles_but_explicit_quote_gap():
    d=capture(('XRPEUR',));d['reference_quote_capture']=reference()
    b=build_packages(d,news(),now=NOW+timedelta(seconds=31))['packages'][0]['package']
    assert 'reference_quote_unavailable_or_stale' in b['missing_evidence']
    assert 'reference_quote' not in b['sources'][b['source_ids'][0]]


def test_reference_capture_uses_only_two_fixed_public_gets():
    calls=[];data=reference()['payload']
    class Response:
        status_code=200
        def __init__(self,p):self.p=p
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,*a):yield json.dumps(self.p).encode()
    class Session:
        def get(self,url,**kw):
            calls.append(url)
            assert kw['allow_redirects'] is False and kw['params']=={'pair':'XRPEUR'}
            return Response(data['asset_pairs' if url.endswith('AssetPairs') else 'tickers'])
    result=capture_quotes(['XRPEUR'],session=Session(),clock=lambda:NOW)
    assert result['status']=='ok' and len(calls)==2
    assert all(x.startswith('https://api.kraken.com/0/public/') for x in calls)


def test_crypto_transport_retry_is_bounded_and_http_errors_are_not_retried():
    import requests
    from market_radar_ai.evidence.crypto_feed import fetch_crypto_feed
    from email.utils import format_datetime
    body=f'<rss><channel><item><title>Crypto report</title><link>https://www.coindesk.com/markets/test</link><pubDate>{format_datetime(NOW)}</pubDate><category>XRP</category></item></channel></rss>'.encode()
    class Response:
        def __init__(self,status):self.status_code=status
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,*a):yield body
    class Session:
        calls=0
        def __init__(self,status):self.status=status
        def get(self,*a,**kw):
            self.calls+=1
            assert kw['allow_redirects'] is False
            if self.status==200 and self.calls==1:raise requests.Timeout()
            return Response(self.status)
    s=Session(200);f=fetch_crypto_feed(session=s,clock=lambda:NOW)
    assert s.calls==2 and f['items'][0]['symbols']==['COINDESK:XRP']
    s=Session(503);f=fetch_crypto_feed(session=s,clock=lambda:NOW)
    assert s.calls==1 and f['reason']=='http_error' and f['status']=='error'


def enriched_bundle():
    from test_candidate_review import answer
    from market_radar_ai.agents.candidate_review import run
    data=capture(('XRPEUR',));data['reference_quote_capture']=reference();feed=news()
    record=build_packages(data,feed,now=NOW)['packages'][0]
    result=run(record,data,feed,answer,clock=lambda:NOW)
    audit={'schema_version':'paid-candidate-review-v1','state':'completed','trade_authorized':False,
           'result':result,'calls':[{'stage':r['stage'],'state':'received','estimated_cost_microeur':123,
                                    'untrusted_response':r} for r in result['reviews']]}
    return record,data,feed,audit


def test_enriched_archive_fixture_reproduces_exactly_without_paid_calls():
    from pathlib import Path
    from market_radar_ai.dashboard.candidate_delivery import export_archive
    fixture=json.loads((Path(__file__).parent/'fixtures/candidate-review-enriched-v1.json').read_text())
    assert export_archive(*json.loads(json.dumps(enriched_bundle())))==fixture
