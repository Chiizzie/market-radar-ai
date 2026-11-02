import json
from types import SimpleNamespace
from datetime import datetime,timezone
from pathlib import Path
import pytest
from test_research_eval_v2 import Client
from market_radar_ai.agents.research_eval_v3 import (
    run,fixtures,Decision,decide,validate_report,Assessment,aggregate)
from market_radar_ai.agents.roles import AgentRole


class V3Client(Client):
    def call(self,**kwargs):
        result=super().call(**kwargs)
        if kwargs['request_id'].endswith(':decision'):
            result.data.pop('unresolved_blocker_ids')
            result.data.pop('caution_ids')
        return result


def test_ids_generated_by_code_not_model(tmp_path):
    client=V3Client();result=run(client,now=datetime.now(timezone.utc),path=tmp_path/'report.json')
    assert all(result['checks'].values()) and len(result['calls'])==16
    assert result['cases'][0]['caution_ids'] and not result['cases'][0]['unresolved_blocker_ids']
    assert result['cases'][1]['unresolved_blocker_ids']
    for request in client.requests:
        assert request['reasoning_effort']=='low'
        assert 'expected_disposition' not in request['prompt']
        assert json.loads(request['prompt'])['case']['computed_plan']['planned_loss_eur']=='11'


def test_real_bad_risk_claim_is_detected_without_masking_it():
    record=json.loads(Path('docs/evaluations/research-eval-v2-partial.json').read_text())
    raw=record['calls'][-1]['data']
    case=fixtures()[1][0]
    assessment=Assessment.model_validate(raw)
    # NBSP in the actual response is harmless whitespace, but risk arithmetic is not.
    validate_report(assessment,AgentRole.OPPORTUNITY_HUNTER,case)
    decision=Decision(case_id=case['case_id'],verdict='reject',rationale='No action')
    result=decide(case,[assessment],aggregate([assessment]),decision)
    assert result['issue_fact_conflicts']==[{'role':'opportunity_hunter','code':'excess_planned_risk'}]
    assert result['research_disposition']=='NO_ACTION'


def test_whitespace_tolerance_does_not_accept_changed_prices():
    record=json.loads(Path('docs/evaluations/research-eval-v2-partial.json').read_text())
    raw=record['calls'][-1]['data']
    raw['citations'][0]['quote']='VWAP is 95.4'
    with pytest.raises(ValueError,match='unsupported_citation'):
        validate_report(Assessment.model_validate(raw),AgentRole.OPPORTUNITY_HUNTER,fixtures()[1][0])


def test_source_schema_and_resume_preserve_rejected_evidence(tmp_path):
    from market_radar_ai.agents.research_eval_v3 import constrained_schema
    case=fixtures()[1][0]
    schema=constrained_schema(Assessment,case,'opportunity_hunter')
    assert schema['$defs']['Issue']['properties']['source_ids']['items']['enum']==[s['id'] for s in case['sources']]
    assert 'case' not in schema['$defs']['Citation']['properties']['source_id']['enum']
    prior=json.loads(Path('docs/evaluations/research-eval-v3-partial.json').read_text())
    class RepairClient(V3Client):
        def call(self,**kwargs):
            # The test client recognizes the role stage; retain the actual request ID in its record.
            original=kwargs['request_id']
            kwargs['request_id']=original.removesuffix(':source-schema-repair')
            response=super().call(**kwargs)
            self.requests[-1]['request_id']=original
            return response
    client=RepairClient()
    result=run(client,now=datetime.now(timezone.utc),path=tmp_path/'report.json',prior_report=prior)
    assert result['reused_responses']==8 and result['new_model_requests']==8
    assert len(result['rejected_calls'])==1 and all(result['checks'].values())
    assert client.requests[0]['request_id'].endswith(':source-schema-repair')
