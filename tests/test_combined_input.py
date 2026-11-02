from datetime import timedelta
import pytest
from test_news_input import feed, NOW
from market_radar_ai.market_data.models import Candle, ProviderResult
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.agents.combined_input import build_combined_input, CombinedResearchInput


def capture(**changes):
    candles=[Candle(symbol='NVDA',interval='5m',timestamp=NOW-timedelta(minutes=n),
        open=100,high=102,low=99,close=101,volume=1000,quote_currency='USD',source='fixture') for n in (15,10,5)]
    result=ProviderResult(provider='fixture',retrieved_at=NOW,candles=candles,**changes)
    return capture_markets(['NVDA'],[],stock_fetch=lambda s:result,crypto_fetch=None,now=NOW)


def test_combined_packet_preserves_currency_candles_and_citations():
    packet=build_combined_input(capture(),feed(),symbol='NVDA',now=NOW)
    assert packet.market.quote_currency=='USD'
    assert len(packet.market.candles)==3
    assert packet.source_ids[-1]==packet.market.source_id()
    assert CombinedResearchInput.model_validate(packet.model_dump(mode='json')).digest()==packet.digest()
    assert not packet.trade_authorized


@pytest.mark.parametrize('case',['checksum','wrong_symbol','stale','partial','duplicate_capture'])
def test_unusable_capture_blocks_research(case):
    document=capture()
    now=NOW
    if case=='checksum':document['captures'][0]['payload']['candles'][0]['close']='102'
    if case=='wrong_symbol':document['captures'][0]['requested_symbol']='MSFT'
    if case=='stale':now=NOW+timedelta(hours=1)
    if case=='partial':document=capture(status='partial')
    if case=='duplicate_capture':document['captures']*=2
    with pytest.raises(ValueError):build_combined_input(document,feed(),symbol='NVDA',now=now)


@pytest.mark.parametrize('case',['currency','source','incomplete','gap','nonfinite','citation'])
def test_restored_packet_rechecks_market_evidence(case):
    data=build_combined_input(capture(),feed(),symbol='NVDA',now=NOW).model_dump(mode='json')
    rows=data['market']['candles']
    if case=='currency': rows[0]['quote_currency']='EUR'
    if case=='source': rows[0]['source']='other'
    if case=='incomplete':rows[-1]['timestamp']=NOW.isoformat()
    if case=='gap':rows.pop(1)
    if case=='nonfinite':rows[0]['volume']='Infinity'
    if case=='citation':data['source_ids']=['invented']
    with pytest.raises(ValueError):CombinedResearchInput.model_validate(data)


def test_combined_evidence_runs_full_mock_debate_without_trade_authority(tmp_path):
    from market_radar_ai.agents.roles import AgentRole
    from market_radar_ai.agents.paper_team import SimulatedAgent
    from market_radar_ai.agents.model_gateway import ModelReply,MockTransport,ModelGateway
    from market_radar_ai.agents.spending import SpendingLedger
    from market_radar_ai.agents.debate import DebateCoordinator,Rebuttal,Adjudication
    packet=build_combined_input(capture(),feed(),symbol='NVDA',now=NOW)
    replies=[ModelReply(SimulatedAgent(role,stance='abstain',source=packet.source_ids[-1]).analyse(packet).model_dump_json()) for role in AgentRole]
    for i,role in enumerate(AgentRole,1):
        responder=AgentRole.TECHNICAL_ANALYST if role!=AgentRole.TECHNICAL_ANALYST else AgentRole.DEVILS_ADVOCATE
        replies.append(ModelReply(Rebuttal(objection_id=f'O{i}',responder=responder,
            explanation='Price and news do not establish broker eligibility or EUR risk.',
            source_ids=packet.source_ids).model_dump_json()))
    replies.append(ModelReply(Adjudication(snapshot_id=packet.digest(),verdict='reject',
        rationale='Missing trade prerequisites',unresolved_ids=tuple(f'O{i}' for i in range(1,7))).model_dump_json()))
    transport=MockTransport(replies)
    coordinator=DebateCoordinator(ModelGateway(transport,SpendingLedger(tmp_path/'budget.db',200)))
    result=coordinator.run(packet,run_id='combined',now=NOW)
    assert len(result.reports)==6 and len(result.rebuttals)==6
    assert result.final.verdict=='reject' and len(result.final.unresolved_ids)==6
    assert len(transport.requests)==13
    assert all('reports' not in r and r['snapshot']==packet.model_dump(mode='json') for r in transport.requests[:6])
    from test_paper_team import plan
    with pytest.raises(ValueError):coordinator.run_paper(packet,plan=plan(),run_id='blocked',now=NOW)
    assert len(transport.requests)==13
