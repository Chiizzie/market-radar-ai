from datetime import timedelta
import pytest
from test_paper_team import snapshot, plan, agents, NOW
from market_radar_ai.agents.paper_team import PaperTeam
from market_radar_ai.storage import TeamAuditStore, run_and_record


def test_roundtrip_and_retry_does_not_repeat_agent_calls(tmp_path):
    path = tmp_path/'audit.sqlite3'
    store, team, item = TeamAuditStore(path), PaperTeam(agents()), snapshot()
    result = run_and_record(team, item, run_id='one', store=store, now=NOW, plan=plan())
    assert TeamAuditStore(path).load('one') == (item, result)
    assert run_and_record(team, item, run_id='one', store=store, now=NOW, plan=plan()) == result
    assert team.budget.used == 7


def test_conflicting_runs_cannot_overwrite_evidence(tmp_path):
    store, team, item = TeamAuditStore(tmp_path/'audit.db'), PaperTeam(agents()), snapshot()
    result = team.run(item, now=NOW, plan=plan())
    store.save('one', item, result)
    with pytest.raises(ValueError): store.save('one', item, result.model_copy(update={'decided_at':NOW+timedelta(seconds=1)}))
    with pytest.raises(ValueError): store.save('bad', snapshot(candidate_id='other'), result)
    assert store.load('one')[1] == result


def test_failed_persistence_does_not_return_decision():
    class Broken:
        def load(self, run_id): raise KeyError(run_id)
        def save(self, *args): raise OSError('disk full')
    with pytest.raises(OSError):
        run_and_record(PaperTeam(agents()), snapshot(), run_id='one', store=Broken(), now=NOW, plan=plan())


def test_no_action_is_also_preserved(tmp_path):
    store, item = TeamAuditStore(tmp_path/'audit.db'), snapshot(quality_passed=False)
    result = run_and_record(PaperTeam(agents()), item, run_id='blocked', store=store, now=NOW)
    assert result.verdict == 'NO_ACTION' and store.load('blocked')[1] == result
