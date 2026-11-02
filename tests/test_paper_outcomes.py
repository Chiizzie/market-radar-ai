from datetime import timedelta
from decimal import Decimal
import pytest
from test_paper_team import NOW, plan
from market_radar_ai.agents.paper_outcomes import Quote, replay_long


def q(minutes,bid,ask):
    return Quote(observed_at=NOW+timedelta(minutes=minutes),bid=bid,ask=ask)


def replay(rows, p=None):
    return replay_long(p or plan(),rows,decision_at=NOW,entry_expires_at=NOW+timedelta(minutes=5))


def test_target_costs_and_spread():
    result=replay([q(0,'99.9','100'),q(1,'102','102.1')])
    assert result.status=='closed' and result.net_pnl_eur==Decimal(19)


def test_gap_through_stop_can_exceed_planned_risk():
    result=replay([q(0,'99.9','100'),q(1,'97','97.1')])
    assert result.exit_fill==97 and result.net_pnl_eur==Decimal(-31)


def test_no_fill_after_expiry():
    assert replay([q(5,99.9,100)]).status=='not_filled'


def test_late_quote_does_not_fake_deadline_exit():
    result=replay([q(0,99.9,100),Quote(observed_at=plan().exit_by+timedelta(seconds=1),bid=101,ask=102)])
    assert result.status=='unresolved' and result.net_pnl_eur is None


def test_exact_deadline_closes():
    result=replay([q(0,99.9,100),Quote(observed_at=plan().exit_by,bid=101,ask=102)])
    assert result.status=='closed' and result.reason=='deadline'


def test_invalid_market_data_rejected():
    with pytest.raises(ValueError): replay([q(0,101,100)])
    with pytest.raises(ValueError): replay([q(1,99,100),q(0,99,100)])


def test_invalidated_entry_not_filled():
    assert replay([q(0,97,98)]).reason=='entry_already_invalidated'


def test_accepted_debate_links_to_durable_outcome(tmp_path):
    from test_debate import build
    from market_radar_ai.agents.debate_store import DebateStore, run_recorded_debate
    from market_radar_ai.agents.paper_outcomes import record_replay
    item,_,team=build(tmp_path)
    store=DebateStore(tmp_path/'audit.db')
    run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=store)
    quotes=[q(0,'99.9',100),q(1,102,'102.1')]
    result=record_replay(store,'one',quotes,entry_expires_at=NOW+timedelta(minutes=5))
    assert result.net_pnl_eur==19
    assert record_replay(store,'one',quotes,entry_expires_at=NOW+timedelta(minutes=5))==result
    with pytest.raises(ValueError):
        record_replay(store,'one',[q(0,99.9,100)],entry_expires_at=NOW+timedelta(minutes=5))
