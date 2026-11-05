from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from market_radar_ai.agents.decision_policy import PolicyFacts,mandatory_blocks,issue_severity
from market_radar_ai.agents.research_eval_v2 import fixtures,decide,Decision

CASE=fixtures()[0][0]
NOW=datetime.fromisoformat(CASE['as_of_dublin'])


def test_supported_facts_and_caution_classification():
    assert mandatory_blocks(PolicyFacts.model_validate(CASE['facts']),NOW)==[]
    assert issue_severity('routine_uncertainty')=='caution'
    assert issue_severity('broker_unverified')=='blocker'
    with pytest.raises(ValueError): issue_severity('ignore_policy')


@pytest.mark.parametrize('key,value,expected',[
    ('broker_verified',False,'broker_unverified'),
    ('broker','robinhood_europe','broker_unverified'),
    ('broker_verified_until',NOW.isoformat(),'broker_expired'),
    ('observed_at',(NOW-timedelta(seconds=601)).isoformat(),'stale_or_incomplete_data'),
    ('observed_at',(NOW+timedelta(seconds=1)).isoformat(),'stale_or_incomplete_data'),
    ('completed_candles',False,'stale_or_incomplete_data'),
    ('currency','USD','currency_mismatch'),
])
def test_non_overridable_constraints(key,value,expected):
    facts=deepcopy(CASE['facts']);facts[key]=value
    assert expected in mandatory_blocks(PolicyFacts.model_validate(facts),NOW)


def test_costs_count_toward_twenty_euro_limit():
    facts=deepcopy(CASE['facts']);facts['plan']['quantity']='20'
    assert 'excess_planned_risk' in mandatory_blocks(PolicyFacts.model_validate(facts),NOW)
    facts['plan']['quantity']='19'
    assert 'excess_planned_risk' not in mandatory_blocks(PolicyFacts.model_validate(facts),NOW)


def test_overnight_and_exact_irish_cutoff():
    facts=deepcopy(CASE['facts'])
    facts['plan']['exit_by']=(NOW+timedelta(days=1)).isoformat()
    assert 'time_rule' in mandatory_blocks(PolicyFacts.model_validate(facts),NOW)
    # Irish summer time: 21:00 UTC is 22:00 Dublin.
    summer=datetime(2026,7,1,21,tzinfo=timezone.utc)
    facts['plan']['exit_by']=(summer+timedelta(minutes=1)).isoformat()
    assert 'time_rule' in mandatory_blocks(PolicyFacts.model_validate(facts),summer)


def test_model_cannot_hide_broker_problem_by_omitting_issues():
    case=fixtures()[1][0]
    final=Decision(case_id=case['case_id'],verdict='support',rationale='wrong',unresolved_blocker_ids=(),caution_ids=())
    result=decide(case,[],[],final)
    assert result['research_disposition']=='NO_ACTION' and not result['decision_consistent']
    assert result['mandatory_blocks']==['broker_unverified']


@pytest.mark.parametrize('day', [7,8])
def test_weekend_is_blocked_even_with_fresh_verified_inputs(day):
    now=datetime(2026,11,day,15,tzinfo=timezone.utc)
    facts=deepcopy(CASE['facts'])
    facts['observed_at']=now.isoformat()
    facts['broker_verified_until']=(now+timedelta(hours=1)).isoformat()
    facts['plan']['exit_by']=(now+timedelta(hours=1)).isoformat()
    assert mandatory_blocks(PolicyFacts.model_validate(facts),now)==['time_rule']
