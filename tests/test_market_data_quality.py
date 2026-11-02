from datetime import datetime, timedelta, timezone
from decimal import Decimal
from market_radar_ai.market_data.models import Candle
from market_radar_ai.market_data.quality import validate_candles

def make_candle(stamp):
    return Candle(symbol="BTC/EUR", interval="5m", timestamp=stamp, open=Decimal("100"),
        high=Decimal("105"), low=Decimal("99"), close=Decimal("103"), volume=Decimal("2"),
        quote_currency="EUR", source="test")

def test_flags_stale_candle():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    assert any(i.code == "stale_candle" for i in validate_candles([make_candle(now-timedelta(minutes=20))], now=now, max_age_seconds=300))

def test_flags_gap():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    rows = [make_candle(now-timedelta(minutes=15)), make_candle(now-timedelta(minutes=5))]
    assert any(i.code == "candle_gap" for i in validate_candles(rows, now=now, expected_interval_seconds=300))

def test_clean_series_has_no_issues():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    rows = [make_candle(now-timedelta(minutes=10)), make_candle(now-timedelta(minutes=5))]
    assert validate_candles(rows, now=now, max_age_seconds=900, expected_interval_seconds=300) == []


def test_historical_rows_do_not_make_fresh_series_stale():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    rows = [make_candle(now-timedelta(minutes=i)) for i in range(60, 0, -5)]
    assert validate_candles(rows, now=now, max_age_seconds=600, expected_interval_seconds=300) == []


def test_empty_series_fails_quality():
    assert validate_candles([])[0].code == 'empty_candles'
