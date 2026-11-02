from datetime import timedelta
from test_debate import build
from test_paper_team import NOW, plan
from test_paper_outcomes import q
from market_radar_ai.agents.debate_store import DebateStore, run_recorded_debate
from market_radar_ai.agents.paper_outcomes import record_replay
from market_radar_ai.agents.reporting import export_run, outcome_summary


def test_report_distinguishes_unmeasured_and_unresolved(tmp_path):
    item,_,team=build(tmp_path)
    store=DebateStore(tmp_path/'audit.db')
    run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=store)
    report=export_run(store,'one')
    assert len(report['reports'])==6 and report['paper_outcome'] is None
    assert report['agent_accuracy'] is None and report['mode']=='SIMULATED_RESEARCH'
    record_replay(store,'one',[q(0,99.9,100)],entry_expires_at=NOW+timedelta(minutes=5))
    summary=outcome_summary(store)
    assert summary['unresolved']==1 and summary['net_pnl_eur'] is None


def test_closed_replay_summary(tmp_path):
    item,_,team=build(tmp_path)
    store=DebateStore(tmp_path/'audit.db')
    run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=store)
    record_replay(store,'one',[q(0,99.9,100),q(1,102,102.1)],entry_expires_at=NOW+timedelta(minutes=5))
    summary=outcome_summary(store)
    assert summary['closed']==1 and summary['net_pnl_eur']=='19'
    assert summary['profitable_closed_fraction']==1 and summary['agent_accuracy'] is None
