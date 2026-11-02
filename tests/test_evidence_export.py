from datetime import datetime,timezone,timedelta
import pytest
from market_radar_ai.dashboard.evidence import export_evidence
from market_radar_ai.evidence.news import parse_news
NOW=datetime(2026,11,2,15,tzinfo=timezone.utc)


def test_unavailable_is_not_empty_success():
    assert export_evidence(None,now=NOW)['status']=='not_connected'
    assert export_evidence({'status':'error','items':[{'bad':'data'}]},now=NOW)['items']==[]
    assert export_evidence({'status':'ok','retrieved_at':NOW.isoformat(),'items':[]},now=NOW)['status']=='ok'


def test_age_is_recalculated_and_extra_fields_are_removed():
    feed=parse_news({'feed':[{'title':'Example','source':'Example','url':'https://example.com/news',
        'time_published':'20261102T143000'}]},now=NOW)
    feed['items'][0]['secret']='not exported'
    result=export_evidence(feed,now=NOW+timedelta(hours=2))
    assert result['status']=='stale'
    assert not result['items'][0]['intraday_recent']
    assert 'secret' not in result['items'][0]


def test_invalid_links_do_not_reach_browser():
    feed=parse_news({'feed':[{'title':'Example','source':'Example','url':'https://example.com/news',
        'time_published':'20261102T143000'}]},now=NOW)
    feed['items'][0]['url']='javascript:alert(1)'
    with pytest.raises(ValueError):export_evidence(feed,now=NOW)
