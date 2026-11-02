import pytest
from test_paper_team import snapshot, NOW
from market_radar_ai.agents.roles import AgentRole
from market_radar_ai.agents.paper_team import SimulatedAgent
from market_radar_ai.agents.model_gateway import ModelGateway, MockTransport, ModelReply
from market_radar_ai.agents.spending import SpendingLedger


def setup(tmp_path, replies, cap=100):
    transport=MockTransport(replies)
    ledger=SpendingLedger(tmp_path/'spend.db',cap)
    return ModelGateway(transport,ledger),transport,ledger


def test_all_roles_roundtrip_without_peer_reports(tmp_path):
    item=snapshot()
    replies=[ModelReply(SimulatedAgent(r,stance='support',source='fixture').analyse(item).model_dump_json()) for r in AgentRole]
    gateway,transport,_=setup(tmp_path,replies)
    reports=[gateway.analyse(r,item,request_id=r.value,maximum_microeur=10,now=NOW) for r in AgentRole]
    assert len(reports)==6 and len(transport.requests)==6
    assert all('reports' not in req for req in transport.requests)


def test_unknown_usage_keeps_reservation(tmp_path):
    gateway,transport,ledger=setup(tmp_path,[TimeoutError()],10)
    with pytest.raises(TimeoutError): gateway.analyse(AgentRole.NEWS_ANALYST,snapshot(),request_id='one',maximum_microeur=10,now=NOW)
    with pytest.raises(RuntimeError): ledger.reserve('two',1,NOW)
    assert len(transport.requests)==1


def test_budget_failure_never_calls_transport(tmp_path):
    gateway,transport,_=setup(tmp_path,[],0)
    with pytest.raises(RuntimeError): gateway.analyse(AgentRole.NEWS_ANALYST,snapshot(),request_id='one',maximum_microeur=10,now=NOW)
    assert not transport.requests


def test_malformed_response_cannot_become_report(tmp_path):
    gateway,_,_=setup(tmp_path,[ModelReply('{bad json')])
    with pytest.raises(ValueError): gateway.analyse(AgentRole.NEWS_ANALYST,snapshot(),request_id='one',maximum_microeur=10,now=NOW)


def test_live_transport_disabled(tmp_path):
    with pytest.raises(ValueError): ModelGateway(object(),SpendingLedger(tmp_path/'spend.db',100))


def test_complete_gateway_team_flow(tmp_path):
    from test_paper_team import plan
    from market_radar_ai.agents.paper_team import PaperTeam
    from market_radar_ai.agents.model_gateway import GatewayAgent
    item=snapshot()
    replies=[ModelReply(SimulatedAgent(r,stance='support',source='fixture').analyse(item).model_dump_json()) for r in AgentRole]
    gateway,transport,_=setup(tmp_path,replies)
    team=PaperTeam([GatewayAgent(r,gateway,run_id='integration',now=NOW) for r in AgentRole])
    result=team.run(item,now=NOW,plan=plan())
    assert result.verdict=='PAPER_PLAN' and len(transport.requests)==6
    assert result.simulated and result.cost_eur==0
