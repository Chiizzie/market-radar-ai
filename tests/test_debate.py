import pytest
from test_paper_team import snapshot, NOW
from market_radar_ai.agents.paper_team import SimulatedAgent
from market_radar_ai.agents.roles import AgentRole
from market_radar_ai.agents.model_gateway import MockTransport, ModelReply, ModelGateway
from market_radar_ai.agents.spending import SpendingLedger
from market_radar_ai.agents.debate import DebateCoordinator, Rebuttal, Adjudication


def build(tmp_path, objection=False, erase=False):
    item=snapshot()
    replies=[ModelReply(SimulatedAgent(r,stance='support',source='fixture',objections=('Check catalyst',) if objection and r==AgentRole.DEVILS_ADVOCATE else ()).analyse(item).model_dump_json()) for r in AgentRole]
    if objection:
        replies.append(ModelReply(Rebuttal(objection_id='O1',responder=AgentRole.TECHNICAL_ANALYST,explanation='Cannot verify catalyst from prices',source_ids=('fixture',)).model_dump_json()))
    replies.append(ModelReply(Adjudication(snapshot_id=item.digest(),verdict='reject' if objection and not erase else 'support',rationale='Fixture only',unresolved_ids=('O1',) if objection and not erase else ()).model_dump_json()))
    transport=MockTransport(replies)
    gateway=ModelGateway(transport,SpendingLedger(tmp_path/'budget.db',100))
    return item,transport,DebateCoordinator(gateway)


def test_all_independent_passes_precede_final(tmp_path):
    item,transport,team=build(tmp_path)
    result=team.run(item,run_id='one',now=NOW)
    assert result.final.verdict=='support' and len(transport.requests)==7
    assert all('reports' not in r for r in transport.requests[:6])
    assert transport.requests[-1]['stage']=='adjudication'


def test_rebuttal_and_unresolved_objection_are_preserved(tmp_path):
    item,transport,team=build(tmp_path,True)
    result=team.run(item,run_id='one',now=NOW)
    assert result.final.verdict=='reject' and len(result.rebuttals)==1
    assert result.final.unresolved_ids==('O1',) and len(transport.requests)==8


def test_model_cannot_silently_erase_objection(tmp_path):
    item,_,team=build(tmp_path,True,True)
    with pytest.raises(ValueError,match='resolution'):
        team.run(item,run_id='one',now=NOW)


def test_paper_boundary_rejects_before_any_request(tmp_path):
    from test_paper_team import plan
    item,transport,team=build(tmp_path)
    with pytest.raises(ValueError):
        team.run_paper(item,plan=plan(quantity=30),run_id='one',now=NOW)
    assert transport.requests==[]


def test_debate_rejection_removes_paper_plan(tmp_path):
    from test_paper_team import plan
    item,_,team=build(tmp_path,True)
    outcome,accepted=team.run_paper(item,plan=plan(),run_id='one',now=NOW)
    assert accepted is None and outcome.final.verdict=='reject'
