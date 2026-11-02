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
