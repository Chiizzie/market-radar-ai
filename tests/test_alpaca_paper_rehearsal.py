from copy import deepcopy
from datetime import timedelta
import pytest
from test_paper_planner import inputs, NOW, run
from market_radar_ai.agents.alpaca_paper_rehearsal import build


def packet():
    rows, cat, fx=inputs()
    for r in rows: r['source']='alpaca_iex'
    capture=dict(version='alpaca-data-check-v1',observed_at=NOW.isoformat(),symbol='NVDA',
                 currency='USD',feed='iex',trade_authorized=False,
                 bars=dict(status='fresh',candles=rows),quote=dict(status='fresh'),
                 news=dict(status='accessible',count=20,catalysts_verified=False))
    return capture,cat,fx


def test_alpaca_draft_preserves_blockers_and_provenance():
    result=build(*packet(),now=NOW)
    assert result['state']=='conditional_paper_draft'
    assert result['plan']['market_source']=='alpaca_iex'
    assert 'iex_limited_market_coverage' in result['blockers']
    assert 'live_bid_ask_and_costs_not_verified' in result['blockers']
    assert 'independent_catalyst_review_pending' in result['blockers']
    assert not result['trade_authorized']

@pytest.mark.parametrize('fault',['old','future','wrong_symbol','wrong_feed','mixed','authorized'])
def test_capture_rejects_mismatch_and_staleness(fault):
    capture,cat,fx=packet()
    if fault=='old':capture['observed_at']=(NOW-timedelta(minutes=6)).isoformat()
    if fault=='future':capture['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='wrong_symbol':capture['symbol']='MSFT'
    if fault=='wrong_feed':capture['feed']='sip'
    if fault=='mixed':capture['bars']['candles'][0]['source']='yahoo_finance'
    if fault=='authorized':capture['trade_authorized']=True
    result=build(capture,cat,fx,now=NOW)
    assert result['plan'] is None
    assert result['failures']==['alpaca_capture_invalid_or_stale']


def test_minimum_count_is_reported_explicitly():
    capture,cat,fx=packet()
    capture['bars']['candles']=capture['bars']['candles'][1:]
    result=build(capture,cat,fx,now=NOW)
    assert result['market_evidence']['candle_count']==19
    assert 'insufficient_completed_candles' in result['failures']
    assert result['plan'] is None


def test_planner_rejects_mixed_sources_and_irregular_spacing():
    rows,cat,fx=inputs()
    rows[0]['source']='alpaca_iex'
    assert 'market_source_unsupported_or_mixed' in run((rows,cat,fx))['failures']
    rows,cat,fx=inputs()
    rows[0]['timestamp']+=timedelta(seconds=10)
    assert 'market_candle_spacing_invalid' in run((rows,cat,fx))['failures']
