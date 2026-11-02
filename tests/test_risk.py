from datetime import datetime
from zoneinfo import ZoneInfo
from market_radar_ai.risk import mandatory_risk_check

def test_risk_ceiling_is_hard_limit():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    assert mandatory_risk_check(20, True, True, True, now).passed
    assert not mandatory_risk_check(20.01, True, True, True, now).passed

def test_live_mode_is_rejected():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    result = mandatory_risk_check(5, False, True, True, now)
    assert not result.passed
    assert "paper_trading_only must be true" in result.failures

def test_intraday_cutoff_is_dublin_time():
    now = datetime(2026, 11, 2, 22, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    assert not mandatory_risk_check(5, True, True, True, now).passed


def test_invalid_loss_and_overnight_are_rejected():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo('Europe/Dublin'))
    for value in (float('nan'), float('inf'), -1):
        assert not mandatory_risk_check(value, True, True, True, now).passed
    assert not mandatory_risk_check(5, True, True, False, now).passed
    assert not mandatory_risk_check(5, True, True, True, now.replace(tzinfo=None)).passed


def test_summer_cutoff_uses_dublin_not_utc():
    from datetime import timezone
    now = datetime(2026, 7, 1, 21, 0, tzinfo=timezone.utc)
    assert not mandatory_risk_check(5, True, True, True, now).passed


def test_unknown_or_coerced_flags_cannot_pass():
    now = datetime(2026, 11, 2, 12, tzinfo=ZoneInfo('Europe/Dublin'))
    for bad in ('false', 'true', 1, 0, None, [], {}):
        for index in range(1, 4):
            args = [5, True, True, True, now]
            args[index] = bad
            assert not mandatory_risk_check(*args).passed


def test_malformed_loss_and_clock_fail_closed():
    now = datetime(2026, 11, 2, 12, tzinfo=ZoneInfo('Europe/Dublin'))
    for bad in (True, False, '5', None, {}, []):
        assert not mandatory_risk_check(bad, True, True, True, now).passed
    for bad in (None, '2026-11-02', 0):
        assert not mandatory_risk_check(5, True, True, True, bad).passed


def test_policy_boolean_fields_reject_coercion():
    from pydantic import TypeAdapter, ValidationError
    from market_radar_ai.agents.decision_policy import PolicyFacts
    import pytest
    for field in ('broker_verified', 'completed_candles'):
        from typing import Annotated
        definition = PolicyFacts.model_fields[field]
        adapter = TypeAdapter(Annotated[definition.annotation, *definition.metadata])
        for bad in ('true', 'false', 1, 0, None):
            with pytest.raises(ValidationError):adapter.validate_python(bad)
        assert adapter.validate_python(True) is True
