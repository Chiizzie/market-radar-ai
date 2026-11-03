from datetime import timedelta
import pytest
from market_radar_ai.dashboard.briefing import build_briefing
from market_radar_ai.dashboard.export import build_snapshot
from test_earnings_calendar import enriched, NOW
from test_stock_context import document
from test_alpaca_news import parse,payload


def test_factual_briefing_references_news_and_calendar_without_agent_opinions():
    r=build_briefing(enriched(),parse(payload()),now=NOW)
    assert r['stocks_with_context']==1 and r['stocks_without_context']==0
    row=r['rows'][0]
    assert row['symbol']=='MSFT' and row['phase']=='PREMARKET_CONTEXT'
    assert row['daily_bars']==3 and row['intraday_bars']==1
    assert len(row['news_evidence_ids'])==1 and len(row['calendar']['events'])==1
    assert row['calendar']['events'][0]['exact_time'] is None
    assert row['review_status']=='NOT_RUN' and not row['trade_authorized'] and r['model_calls']==0
    assert 'independent_catalyst_confirmation_missing' in row['missing_evidence']


def test_stale_context_is_counted_missing_instead_of_redated():
    r=build_briefing(enriched(),None,now=NOW+timedelta(minutes=16))
    assert r['rows']==[] and r['stocks_without_context']==1


def test_missing_calendar_stays_unavailable():
    assert build_briefing(document(),None,now=NOW)['rows'][0]['calendar'] is None


def test_bad_calendar_hash_blocks_export():
    d=enriched();d['earnings_calendars'][0]['payload']['events']=[]
    with pytest.raises(ValueError,match='checksum'):build_briefing(d,None,now=NOW)


def test_legacy_snapshot_unchanged_and_optional_empty_briefing_is_not_coverage():
    from test_dashboard_cache import capture, NOW as CAPTURE_NOW
    d=capture();old=build_snapshot(d,now=CAPTURE_NOW)
    assert 'research_briefing' not in old
    d['stock_context']=[]
    new=build_snapshot(d,now=CAPTURE_NOW)
    briefing=new.pop('research_briefing')
    assert new==old and briefing['stocks_attempted']==0 and briefing['rows']==[]
