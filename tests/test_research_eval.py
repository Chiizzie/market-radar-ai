import json
from decimal import Decimal
from types import SimpleNamespace
import pytest
from test_spending import NOW
from market_radar_ai.agents.research_eval import (
    fixtures, run_evaluation, Assessment, Citation, validate_assessment,
    ResearchDecision, evaluate_decision, collect_objections)
from market_radar_ai.agents.roles import AgentRole


class FakeClient:
    def __init__(self): self.requests=[]
    def call(self,**kwargs):
        self.requests.append(kwargs)
        payload=json.loads(kwargs['prompt']);case=payload['case']
        stage=kwargs['request_id'].split(':')[-1]
        if stage in {r.value for r in AgentRole}:
            data={'role':stage,'case_id':case['case_id'],'stance':'support',
                'rationale':'Fictional evidence supports further review.',
                'citations':[{'source_id':'risk','quote':'Planned loss is 11 EUR',
                              'interpretation':'Below the maximum.'}],
                'objections':[], 'missing_data':[]}
            if case['hard_blocks'] and stage=='risk_manager':
                data.update(stance='oppose',objections=['Broker eligibility unverified'])
        elif stage=='debate':
            data={'responses':[{'objection_id':o['id'],'explanation':'Evidence does not resolve it.',
                                 'source_ids':['broker']} for o in payload['objections']]}
        else:
            data={'case_id':case['case_id'],'verdict':'reject' if case['hard_blocks'] else 'support',
                'rationale':'Final research assessment.',
                'unresolved_ids':[o['id'] for o in payload['objections']]}
        return SimpleNamespace(data=data,response_id='fixture',input_tokens=10,output_tokens=10,
                               cost_usd=Decimal('0.001'),estimated_cost_microeur=900)


def test_two_cases_six_independent_passes_then_debate(tmp_path):
    client=FakeClient()
    result=run_evaluation(client,now=NOW,path=tmp_path/'result.json')
    assert result['state']=='completed' and len(client.requests)==16
    assert result['cases'][0]['research_disposition']=='SUPPORTED_FOR_REVIEW'
    assert result['cases'][1]['research_disposition']=='NO_ACTION'
    for offset in (0,8):
        for request in client.requests[offset:offset+6]:
            assert set(json.loads(request['prompt']))=={'case','role'}
            assert 'instructions' in request
    assert result['estimated_cost_microeur']==14400 and all(result['checks'].values())
    assert all(not c['trade_authorized'] for c in result['cases'])


def test_invented_quote_stops_run_and_saves_paid_reply(tmp_path):
    class BadClient(FakeClient):
        def call(self,**kwargs):
            result=super().call(**kwargs)
            result.data['citations'][0]['quote']='invented quote'
            return result
    path=tmp_path/'failed.json';client=BadClient()
    with pytest.raises(ValueError,match='unsupported_citation'):
        run_evaluation(client,now=NOW,path=path)
    saved=json.loads(path.read_text())
    assert saved['state']=='failed' and len(saved['calls'])==1 and len(client.requests)==1


def test_model_cannot_override_broker_block():
    case=fixtures()[1]
    final=ResearchDecision(case_id=case['case_id'],verdict='support',rationale='unsafe',unresolved_ids=())
    result=evaluate_decision(case,[],[],final)
    assert result['research_disposition']=='NO_ACTION' and result['model_attempted_unsafe_support']


def test_model_cannot_erase_objection():
    case=fixtures()[0]
    final=ResearchDecision(case_id=case['case_id'],verdict='support',rationale='unsafe',unresolved_ids=())
    with pytest.raises(ValueError,match='objection_resolution'):
        evaluate_decision(case,[],[{'id':'O1'}],final)


def test_role_identity_and_support_without_citation():
    case=fixtures()[0]
    report=Assessment(role=AgentRole.NEWS_ANALYST,case_id=case['case_id'],stance='support',
                      rationale='test',citations=(),objections=(),missing_data=())
    with pytest.raises(ValueError,match='identity'):
        validate_assessment(report,AgentRole.RISK_MANAGER,case)
    with pytest.raises(ValueError,match='without_evidence'):
        validate_assessment(report,AgentRole.NEWS_ANALYST,case)


def test_peer_injection_only_in_untrusted_payload(tmp_path):
    client=FakeClient();run_evaluation(client,now=NOW,path=tmp_path/'result.json')
    assert all('IGNORE ALL RULES' not in r['instructions'] for r in client.requests)
    assert 'IGNORE ALL RULES' in client.requests[8]['prompt']


def test_saved_real_prefix_is_reused_and_evidence_checked(tmp_path):
    from pathlib import Path
    saved=json.loads(Path('docs/evaluations/research-eval-v1-partial.json').read_text())
    client=FakeClient()
    # Fake final should preserve the real objections, so no unsafe acceptance.
    result=run_evaluation(client,now=NOW,path=tmp_path/'resumed.json',prior_report=saved)
    assert result['reused_responses']==7 and result['new_model_requests']==9
    assert len(client.requests)==9
    assert client.requests[0]['request_id'].endswith(':decision')
    altered=json.loads(json.dumps(saved));altered['cases'][0]['evidence']['symbol']='CHANGED'
    with pytest.raises(ValueError,match='evidence_mismatch'):
        run_evaluation(FakeClient(),now=NOW,path=tmp_path/'bad.json',prior_report=altered)
