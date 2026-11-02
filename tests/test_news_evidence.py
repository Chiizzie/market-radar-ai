from datetime import datetime, timezone
import pytest
from market_radar_ai.evidence.news import parse_news, EvidenceItem, NewsProvider
NOW=datetime(2026,11,2,15,tzinfo=timezone.utc)
ROW=dict(title='Example announcement',source='Example publisher',url='https://example.com/story',time_published='20261102T140000',ticker_sentiment=[{'ticker':'MSFT'}])


def test_news_preserves_provenance_and_deduplicates():
    r=parse_news({'feed':[ROW,ROW]},now=NOW)
    assert len(r['items'])==1
    assert r['rejected'][0]['reason']=='duplicate_url'
    assert r['items'][0]['verification']=='provider_reported'
    assert not r['trade_authorized']


@pytest.mark.parametrize('patch',[{'time_published':'20261102T160000'},{'url':'javascript:alert(1)'},{'time_published':'bad'}])
def test_invalid_evidence_cannot_enter_feed(patch):
    assert not parse_news({'feed':[{**ROW,**patch}]},now=NOW)['items']


def test_limits_and_stale_items_are_visible():
    r=parse_news({'feed':[ROW,ROW]},now=NOW,limit=1,max_age_seconds=60)
    assert r['deferred']==1 and r['rejected'][0]['reason']=='stale'


def test_missing_credentials_do_not_make_network_request(monkeypatch):
    monkeypatch.delenv('ALPHA_VANTAGE_API_KEY',raising=False)
    assert NewsProvider().fetch()['status']=='not_configured'


def test_disclosure_distinguishes_transaction_from_publication():
    item=EvidenceItem(kind='investor_disclosure',title='Example disclosure',source='Filing',
        url='https://example.com/filing',event_at='2026-10-01T12:00:00Z',published_at=NOW,retrieved_at=NOW)
    assert item.event_at < item.published_at
    with pytest.raises(ValueError):
        EvidenceItem(**{**item.model_dump(),'event_at':'2026-12-01T12:00:00Z'})
