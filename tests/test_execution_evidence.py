from datetime import datetime,timezone,timedelta
import pytest
from market_radar_ai.agents.execution_evidence import assess_quote
NOW=datetime(2026,11,3,17,tzinfo=timezone.utc)

def quote():return dict(timestamp=NOW.isoformat(),bid_usd='199',ask_usd='201')

def test_spread_is_indicative_only():
    r=assess_quote(quote(),now=NOW)
    assert r['spread_bps']=='100.00' and r['spread_usd']=='2'
    assert not r['costs_verified'] and not r['broker_executable']

@pytest.mark.parametrize('change',[dict(bid_usd='NaN'),dict(ask_usd='Infinity'),dict(bid_usd='202'),dict(bid_usd='0'),dict(timestamp=(NOW-timedelta(seconds=121)).isoformat()),dict(timestamp=(NOW+timedelta(seconds=1)).isoformat()),dict(timestamp='2026-11-03T17:00:00')])
def test_invalid_quotes_cannot_support_execution(change):
    r=assess_quote(dict(quote(),**change),now=NOW)
    assert r['status']=='unavailable_or_stale' and 'spread_bps' not in r
