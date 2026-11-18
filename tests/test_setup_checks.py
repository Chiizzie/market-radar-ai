from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest
from market_radar_ai.agents.setup_checks import reference_checks, technical_checks, validate_paper_plan
from market_radar_ai.agents.candidate_plan import draft
from market_radar_ai.agents.combined_input import build_market_evidence
from market_radar_ai.agents.candidate_packages import digest
from test_candidate_packages import capture, NOW
from test_stock_checks import payload, NOW as STOCK_NOW


def plan_and_bars():
    doc=capture()
    bars=build_market_evidence(doc,symbol=doc['captures'][0]['requested_symbol'],now=NOW,market_name='crypto')
    return draft(bars,None,now=NOW),bars


def test_recomputes_risk_and_technical_measurements():
    plan,bars=plan_and_bars()
    result=validate_paper_plan(plan,now=NOW)
    assert result['state']=='PASS' and Decimal(result['recomputed_loss_eur'])<=20
    assert result['verified_broker_costs'] is False
    technical=technical_checks(bars)
    assert technical['state']=='MEASURED'
    assert Decimal(technical['rolling_20_bar_vwap'])>0
    assert technical['trigger_state']=='WAITING_FOR_TRIGGER'


@pytest.mark.parametrize('field,value', [('quantity','10000'),('planned_loss_eur','0'),
    ('entry_eur','NaN'),('target_eur','0'),('currency','USD'),('trade_authorized',True),
    ('assumed_round_trip_cost_eur','-1'),('expires_at','bad')])
def test_invalid_risk_or_scope_never_passes(field,value):
    plan,_=plan_and_bars();plan[field]=value
    assert validate_paper_plan(plan,now=NOW)['state']=='FAIL'


def test_net_target_costs_and_session_deadline_are_enforced():
    plan,_=plan_and_bars()
    plan['target_eur']=str(Decimal(plan['entry_eur'])+Decimal('0.01'))
    assert 'net_reward_below_2r' in validate_paper_plan(plan,now=NOW)['failures']
    plan,_=plan_and_bars()
    assert 'exit_after_market_deadline' in validate_paper_plan(plan,now=NOW,
        exit_deadline=(NOW+timedelta(minutes=10)).isoformat())['failures']


def test_catalogue_and_reference_quote_do_not_prove_broker_permission():
    p=payload();record={'payload':p,'payload_sha256':digest(p)}
    r=reference_checks({'stock_reference_checks':record},symbol='IBM',market='stocks',now=STOCK_NOW)
    assert r['catalogue_candidate']=='PASS' and r['reference_quote']=='PASS'
    assert Decimal(r['indicative_bid_eur'])>0
    assert Decimal(r['indicative_bid_eur'])<=Decimal(r['indicative_ask_eur'])
    assert r['broker_account_permission']==r['broker_quote']==r['verified_costs']=='UNKNOWN'
    assert r['exit_deadline']=='2026-11-04T20:55:00+00:00'
    record['payload_sha256']='bad'
    assert reference_checks({'stock_reference_checks':record},symbol='IBM',market='stocks',now=STOCK_NOW)['market_session']=='UNKNOWN'


def test_closed_stale_and_mismatched_symbol_never_pass_session_check():
    p=payload();p['market_clock']['is_open']=False
    doc={'stock_reference_checks':{'payload':p,'payload_sha256':digest(p)}}
    assert reference_checks(doc,symbol='IBM',market='stocks',now=STOCK_NOW)['market_session']=='FAIL'
    assert reference_checks(doc,symbol='OTHER',market='stocks',now=STOCK_NOW)['market_session']=='UNKNOWN'
    assert reference_checks(doc,symbol='IBM',market='stocks',now=STOCK_NOW+timedelta(seconds=61))['reference_quote']=='UNKNOWN'
