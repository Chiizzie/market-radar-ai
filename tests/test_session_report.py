from datetime import timedelta
import pytest
from test_review_export import bundle, NOW
from market_radar_ai.dashboard.plan_review import export_review
from market_radar_ai.agents.session_report import build_session_report


def test_completed_research_is_not_a_trade_or_scored_result():
    c, cat, draft, audit = bundle()
    review = export_review(c,cat,draft,audit,now=NOW)
    r=build_session_report({'state':'completed'},draft,review,now=NOW)
    assert r['validated_review_completed']
    assert r['session_result']=='REVIEWED_NO_TRADE'
    assert not r['trade_authorized'] and not r['paper_position_opened']
    assert r['outcome']['net_pnl_eur'] is None and r['outcome']['accuracy_score'] is None
    assert 'six_agent_plan_review_not_run' not in r['blocking_reasons']
    assert 'account_specific_eligibility_not_verified' in r['blocking_reasons']


def test_later_report_preserves_expiry_without_relabelling_fresh():
    _,_,draft,_=bundle()
    r=build_session_report({'state':'ready_dry_run'},draft,None,now=NOW+timedelta(hours=1))
    assert not r['checks']['plan_unexpired']
    assert r['session_result']=='UNREVIEWED_NO_TRADE'


@pytest.mark.parametrize('loss',['NaN','Infinity','-1','0','20.01'])
def test_bad_risk_never_passes(loss):
    _,_,draft,_=bundle();draft['plan']['planned_loss_eur']=loss
    r=build_session_report({},draft,None,now=NOW)
    assert not r['checks']['planned_loss_within_eur20']


def test_early_failure_has_no_fake_review_or_zero_pnl():
    r=build_session_report({'state':'blocked_or_failed'},None,None,now=NOW)
    assert not r['validated_review_completed']
    assert r['outcome']['net_pnl_eur'] is None
    assert 'no_conditional_plan' in r['blocking_reasons']
