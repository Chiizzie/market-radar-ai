from datetime import datetime,timezone,timedelta
from market_radar_ai.evidence.combine import combine_feeds
from market_radar_ai.evidence.news import parse_news
NOW=datetime(2026,11,2,15,tzinfo=timezone.utc)


def good():
    return parse_news({'feed':[{'title':'Example','source':'Publisher','url':'https://example.com/story','time_published':'20261102T140000'}]},now=NOW)


def test_failure_is_visible_alongside_success():
    r=combine_feeds([good(),{'status':'error','items':[]}],now=NOW)
    assert r['status']=='partial' and len(r['items'])==1
    assert r['sources'][1]['status']=='error'


def test_deduplication_and_timestamp_preservation():
    r=combine_feeds([good(),good()],now=NOW+timedelta(minutes=1))
    assert len(r['items'])==1 and len(r['rejected'])==1
    assert datetime.fromisoformat(r['retrieved_at'])==NOW


def test_all_stale_sources_are_not_new_evidence():
    r=combine_feeds([good()],now=NOW+timedelta(hours=1))
    assert r['status']=='error' and not r['items']
    assert r['sources'][0]['status']=='stale'


def test_news_acceptance_rejects_empty_company_feed():
    from market_radar_ai.evidence.readiness import assess_news
    empty={**good(),'items':[]}
    assert not assess_news(good(),empty,now=NOW)['news_delivery_verified']
    assert assess_news(good(),good(),now=NOW)['news_delivery_verified']


def test_invalid_company_article_cannot_pass_delivery_acceptance():
    from market_radar_ai.evidence.readiness import assess_news
    invalid = {**good(), 'items': [{'title': 'Incomplete article'}]}
    result = assess_news(good(), invalid, now=NOW)
    assert not result['checks']['company_items_available']
    assert not result['news_delivery_verified']
    combined = combine_feeds([good(), invalid], now=NOW)
    assert combined['sources'][0]['validated_item_count'] == 1
    assert combined['sources'][1]['validated_item_count'] == 0
