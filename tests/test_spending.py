from datetime import datetime, timezone
import pytest
from market_radar_ai.agents.spending import SpendingLedger
from market_radar_ai.agents.prompts import instruction, ROLE_TASKS
from market_radar_ai.agents.roles import AgentRole
NOW=datetime(2026,11,2,12,tzinfo=timezone.utc)


def test_persistence_and_unknown_usage_remains_reserved(tmp_path):
    path=tmp_path/'budget.db'
    SpendingLedger(path,100).reserve('a',80,NOW)
    ledger=SpendingLedger(path,100)
    with pytest.raises(RuntimeError): ledger.reserve('b',21,NOW)
    with pytest.raises(ValueError): ledger.reserve('a',80,NOW)
    ledger.settle('a',30)
    ledger.reserve('b',70,NOW)
    with pytest.raises(RuntimeError): ledger.reserve('c',1,NOW)


def test_overrun_is_recorded_and_blocks_further_spending(tmp_path):
    ledger=SpendingLedger(tmp_path/'budget.db',100)
    ledger.reserve('a',50,NOW)
    with pytest.raises(RuntimeError): ledger.settle('a',120)
    with pytest.raises(RuntimeError): ledger.reserve('b',1,NOW)
    ledger.settle('a',120)
    with pytest.raises(ValueError): ledger.settle('a',1)


def test_all_roles_have_distinct_instructions():
    assert set(ROLE_TASKS)==set(AgentRole)
    assert len({instruction(r) for r in AgentRole})==6


@pytest.mark.parametrize('limit', [-1, True, 1.5])
@pytest.mark.parametrize('name', ['monthly_limit_microeur', 'lifetime_limit_microeur'])
def test_invalid_extended_limits(tmp_path, name, limit):
    with pytest.raises(ValueError):
        SpendingLedger(tmp_path/'budget.db', 100, **{name: limit})


def test_monthly_limit_spans_days_and_resets_at_dublin_month(tmp_path):
    ledger = SpendingLedger(tmp_path/'budget.db', 100, monthly_limit_microeur=150)
    ledger.reserve('a', 90, NOW)
    next_day = NOW.replace(day=3)
    with pytest.raises(RuntimeError, match='monthly_spending_limit'):
        ledger.reserve('b', 61, next_day)
    ledger.reserve('b', 60, next_day)
    ledger.reserve('c', 100, NOW.replace(month=12))


def test_lifetime_pilot_limit_survives_restart_and_new_month(tmp_path):
    path = tmp_path/'budget.db'
    SpendingLedger(path, 100, lifetime_limit_microeur=120).reserve('a', 80, NOW)
    ledger = SpendingLedger(path, 100, lifetime_limit_microeur=120)
    with pytest.raises(RuntimeError, match='lifetime_spending_limit'):
        ledger.reserve('b', 41, NOW.replace(month=12))
    ledger.settle('a', 60)
    ledger.reserve('b', 60, NOW.replace(month=12))


def test_budget_uses_dublin_month_during_summer_time(tmp_path):
    ledger = SpendingLedger(tmp_path/'budget.db', 100, monthly_limit_microeur=100)
    ledger.reserve('a', 100, datetime(2026, 6, 30, 23, 30, tzinfo=timezone.utc))
    with pytest.raises(RuntimeError, match='monthly_spending_limit'):
        ledger.reserve('b', 1, datetime(2026, 7, 2, 12, tzinfo=timezone.utc))
