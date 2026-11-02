from datetime import datetime,timezone
import pytest
from market_radar_ai.evidence.company_news import parse_company_news
NOW=datetime(2026,11,2,15,tzinfo=timezone.utc)
ROW={'content':{'title':'Example','pubDate':'2026-11-02T14:00:00Z','provider':{'displayName':'Publisher'},'canonicalUrl':{'url':'https://example.com/story'}}}


def test_query_is_not_verified_entity_mapping():
    r=parse_company_news([ROW,ROW],symbol='MSFT',now=NOW)
    assert r['query_symbol']=='MSFT' and len(r['items'])==1
    assert r['items'][0]['symbols']==[]
    assert r['rejected'][0]['reason']=='duplicate_url'


def test_missing_fields_and_stale_articles_are_visible():
    row={'content':{**ROW['content'],'pubDate':'2026-10-01T14:00:00Z'}}
    r=parse_company_news([{},row],symbol='MSFT',now=NOW)
    assert not r['items'] and r['status']=='partial'
    assert [i['reason'] for i in r['rejected']]==['invalid_item','stale']


def test_naive_timestamp_rejected():
    row={'content':{**ROW['content'],'pubDate':'2026-11-02T14:00:00'}}
    assert not parse_company_news([row],symbol='MSFT',now=NOW)['items']


def test_empty_wrapper_response_does_not_verify_news_availability():
    r=parse_company_news([],symbol='MSFT',now=NOW)
    assert r['status']=='partial'
    assert r['response_item_count']==0
    assert r['availability_note']=='empty_response_unconfirmed'
