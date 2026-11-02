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
