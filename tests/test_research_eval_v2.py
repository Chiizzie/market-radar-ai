import json
from types import SimpleNamespace
from decimal import Decimal
from datetime import datetime,timezone
from market_radar_ai.agents.research_eval_v2 import run,fixtures
from market_radar_ai.agents.roles import AgentRole


class Client:
    def __init__(self): self.requests=[]
    def call(self,**kwargs):
        self.requests.append(kwargs)
        data=json.loads(kwargs['prompt']);case=data['case'];stage=kwargs['request_id'].split(':')[-1]
        if stage in {r.value for r in AgentRole}:
            blocked=not case['facts']['broker_verified'] and stage=='risk_manager'
            result={'role':stage,'case_id':case['case_id'],'stance':'oppose' if blocked else 'support',
                'rationale':'Synthetic analysis','citations':[{'source_id':'chart','quote':'VWAP is 99.4',
                'interpretation':'Constructive'}], 'issues':[{'code':'broker_unverified' if blocked else 'routine_uncertainty',
                'explanation':'Broker not verified' if blocked else 'Future price movement uncertain',
                'source_ids':['broker'] if blocked else ['chart']}]}
        elif stage=='debate':
            result={'responses':[{'objection_id':i['id'],'explanation':'Preserved','source_ids':[]} for i in data['issues']]}
        else:
            blockers=[i['id'] for i in data['issues'] if i['severity']=='blocker']
            result={'case_id':case['case_id'],'verdict':'reject' if blockers else 'support','rationale':'Review',
                'unresolved_blocker_ids':blockers,'caution_ids':[i['id'] for i in data['issues'] if i['severity']=='caution']}
        return SimpleNamespace(data=result,response_id='mock',input_tokens=10,output_tokens=10,
                               cost_usd=Decimal('0.001'),estimated_cost_microeur=900)


def test_blinded_evaluation_cautions_do_not_veto(tmp_path):
    client=Client();result=run(client,now=datetime.now(timezone.utc),path=tmp_path/'report.json')
    assert len(client.requests)==16 and all(result['checks'].values())
    assert result['cases'][0]['research_disposition']=='SUPPORTED_FOR_REVIEW'
    assert result['cases'][1]['research_disposition']=='NO_ACTION'
    for offset in (0,8):
        for request in client.requests[offset:offset+6]:
            assert set(json.loads(request['prompt']))=={'case','role'}
    for request in client.requests:
        assert 'expected_disposition' not in request['prompt']
        assert 'hard_blocks' not in request['prompt']
        assert 'mandatory_blocks' not in request['prompt']
        assert 'mark broker approval' not in request['instructions']
    assert all(not item['trade_authorized'] for item in result['cases'])
