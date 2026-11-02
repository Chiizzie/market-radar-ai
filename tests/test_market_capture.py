from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest
from market_radar_ai.market_data.capture import capture_result
from market_radar_ai.market_data.models import Candle, ProviderResult

NOW = datetime(2026, 11, 2, 15, 10, tzinfo=timezone.utc)


def result(age=300, **overrides):
    row = Candle(symbol="XBTEUR", interval="5m", timestamp=NOW-timedelta(seconds=age),
                 open=100, high=101, low=99, close=100, volume=10,
                 quote_currency="EUR", source="kraken")
    return ProviderResult(provider="kraken", retrieved_at=NOW, candles=[row], **overrides)


def test_capture_preserves_quotes_and_cannot_authorize():
    output = capture_result(result(), now=NOW)
    p = output["payload"]
    assert p["quality_passed_at_capture"]
    assert p["candles"][0]["close"] == "100"
    assert p["disposition"] == "NO_ACTION"
    assert p["account_broker_eligibility"] == "unknown"
    canonical = json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert output["payload_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()


@pytest.mark.parametrize("age,code", [(1200, "stale_candle"), (60, "incomplete_or_unexpected_interval")])
def test_capture_rejects_unusable_time(age, code):
    p = capture_result(result(age), now=NOW)["payload"]
    assert not p["quality_passed_at_capture"]
    assert code in {issue["code"] for issue in p["quality_issues"]}


def test_failure_is_preserved_and_empty_data_fails():
    p = capture_result(ProviderResult(provider="kraken", retrieved_at=NOW, status="error"), now=NOW)["payload"]
    assert p["provider_status"] == "error"
    assert not p["quality_passed_at_capture"]
    assert p["candles_saved"] == 0


def test_bounds_and_naive_clock_rejected():
    with pytest.raises(ValueError):
        capture_result(result(), now=NOW, limit=121)
    with pytest.raises(ValueError):
        capture_result(result(), now=NOW.replace(tzinfo=None))


def test_duplicate_data_remains_visible():
    data = result()
    data.candles.append(data.candles[0])
    p = capture_result(data, now=NOW)["payload"]
    assert p["candles_saved"] == 2
    assert not p["quality_passed_at_capture"]
