import pytest
from test_debate import build
from test_paper_team import plan, NOW
from market_radar_ai.agents.debate_store import DebateStore, run_recorded_debate


def test_restart_reuses_complete_evidence_without_calls(tmp_path):
    item,transport,team=build(tmp_path)
    path=tmp_path/'audit.db'
    result=run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=DebateStore(path))
    again=run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=DebateStore(path))
    assert result==again and len(transport.requests)==7
    record=DebateStore(path).inspect('one')
    assert record['state']=='completed' and len(record['result']['debate']['reports'])==6
    with pytest.raises(ValueError):
        run_recorded_debate(team,item,plan=plan(quantity=9),run_id='one',now=NOW,store=DebateStore(path))


def test_rejected_debate_and_rebuttal_are_preserved(tmp_path):
    item,_,team=build(tmp_path,True)
    store=DebateStore(tmp_path/'audit.db')
    _,accepted=run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=store)
    assert accepted is None
    assert len(store.inspect('one')['result']['debate']['rebuttals'])==1


def test_failure_blocks_reexecution(tmp_path):
    item,transport,team=build(tmp_path,True,True)
    store=DebateStore(tmp_path/'audit.db')
    with pytest.raises(ValueError):
        run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=store)
    calls=len(transport.requests)
    with pytest.raises(RuntimeError):
        run_recorded_debate(team,item,plan=plan(),run_id='one',now=NOW,store=store)
    assert len(transport.requests)==calls and store.inspect('one')['state']=='failed'


def test_unfinished_run_cannot_be_claimed_twice(tmp_path):
    store=DebateStore(tmp_path/'audit.db')
    assert store.begin('one',{'a':1}) is None
    with pytest.raises(RuntimeError): store.begin('one',{'a':1})
