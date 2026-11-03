from copy import deepcopy
from datetime import timedelta
import hashlib,json
import pytest
from test_capture_shortlist import capture, NOW
from market_radar_ai.agents.candidate_packages import build_packages, verify_package


def stock_capture():
    d=capture(('AMD',))
    d['captures'][0]['market']='stocks'
    d['coverage']['stocks'],d['coverage']['crypto']=d['coverage']['crypto'],d['coverage']['stocks']
    return d


def feed(symbols=('AMD',), age=0):
    return {'status':'ok','scope':'TEST','retrieved_at':NOW.isoformat(),'items':[
        {'kind':'news','title':'A sourced event','source':'Test publisher','url':'https://example.com/event',
         'published_at':(NOW-timedelta(seconds=age)).isoformat(),'retrieved_at':NOW.isoformat(),
         'symbols':symbols}]}


def test_crypto_packages_are_generic_and_not_inferred_from_news_symbols():
    r=build_packages(capture(),feed(('XBTEUR',)),now=NOW)
    assert len(r['packages'])==2 and r['model_calls']==0
    b=verify_package(r['packages'][0],now=NOW)
    assert b['market']=='crypto' and b['intended_broker']=='robinhood_europe'
    assert b['eur_conversion']=='native_eur' and len(b['roles'])==6
    assert not b['news_source_ids'] and b['plan'] is None
    assert not b['trade_authorized']


def test_non_nvda_equity_gets_exact_linked_news_and_citations():
    r=build_packages(stock_capture(),feed(),now=NOW)['packages'][0]
    b=verify_package(r,now=NOW)
    assert b['symbol']=='AMD' and len(b['news_source_ids'])==1
    assert set(b['source_ids'])==set(b['sources'])
    assert 'broker_account_eligibility_unverified' in b['missing_evidence']


@pytest.mark.parametrize('symbols',[(),('NVDA',)])
def test_query_leads_and_other_ticker_news_not_attached(symbols):
    b=build_packages(stock_capture(),feed(symbols),now=NOW)['packages'][0]['package']
    assert not b['news_source_ids']


def test_old_news_marked_context_only_and_stale_retrieval_excluded():
    f=feed(age=7200)
    b=build_packages(stock_capture(),f,now=NOW)['packages'][0]['package']
    assert b['context_only_news_ids']==b['news_source_ids']
    assert 'current_symbol_linked_news_missing' in b['missing_evidence']
    f['items'][0]['retrieved_at']=(NOW-timedelta(seconds=901)).isoformat()
    b=build_packages(stock_capture(),f,now=NOW)['packages'][0]['package']
    assert not b['news_source_ids']


def test_tampering_expiry_and_input_isolation():
    d=capture();original=deepcopy(d)
    r=build_packages(d,None,now=NOW)['packages'][0]
    assert d==original
    with pytest.raises(ValueError,match='expired'):verify_package(r,now=NOW+timedelta(seconds=60))
    r['package']['symbol']='FAKE'
    with pytest.raises(ValueError,match='digest'):verify_package(r,now=NOW)


def test_stale_capture_creates_no_packages():
    assert build_packages(capture(),None,now=NOW+timedelta(hours=1))['packages']==[]


def test_usd_prices_are_never_relabelled_as_eur():
    d=stock_capture(); payload=d['captures'][0]['payload']
    for row in payload['candles']: row['quote_currency']='USD'
    d['captures'][0]['payload_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    b=build_packages(d,feed(),now=NOW)['packages'][0]['package']
    assert b['native_currency']=='USD' and b['reporting_currency']=='EUR'
    assert b['eur_conversion']=='not_supplied'
    assert 'fresh_fx_conversion_missing' in b['missing_evidence']


def test_bad_news_feed_keeps_market_package_with_explicit_gap():
    b=build_packages(stock_capture(),{'status':'ok','items':'invalid'},now=NOW)['packages'][0]['package']
    assert b['news_feed_status']=='error' and not b['news_source_ids']
    assert 'current_symbol_linked_news_missing' in b['missing_evidence']


def test_corrupt_capture_cannot_be_packaged():
    d=capture();d['captures'][0]['payload']['provider']='changed'
    with pytest.raises(ValueError,match='checksum'):build_packages(d,None,now=NOW)
