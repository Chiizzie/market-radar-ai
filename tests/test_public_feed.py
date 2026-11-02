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
