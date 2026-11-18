from datetime import datetime, UTC, timedelta
from market_radar_ai.dashboard.cross_scanner_audit import build

NOW = datetime(2026,11,6,18,50,tzinfo=UTC)


def inputs():
    old={'schema_version':2,'generated_at':(NOW-timedelta(minutes=2)).isoformat(),
         'potential_signals':[{'ticker':'ASH','asset_type':'stock','qualification':{
             'status':'ACTIONABLE NOW','pattern':'TREND_PULLBACK_RECLAIM','plan':{'entry':77.61}}}]}
    trace={'symbols':[{'symbol':'ASH','selection_reason':'outside_technical_budget'}]}
    q={'evaluated_at':NOW.isoformat(),'candidates':[]}
    return old,trace,q


def test_discovery_miss_is_not_an_ai_rejection_or_profit_claim():
    report=build(*inputs(),now=NOW)
    assert report['rows'][0]['ai_stage']=='outside_technical_budget'
    assert not report['rows'][0]['profit_or_loss_inferred']
    assert not report['trade_authorized'] and report['model_calls']==0


def test_stale_original_and_missing_trace_remain_unknown():
    old,trace,q=inputs();old['generated_at']=(NOW-timedelta(hours=1)).isoformat()
    assert build(old,trace,q,now=NOW)['rows'][0]['ai_stage']=='no_contemporaneous_ai_capture'
    old,_,q=inputs()
    assert build(old,None,q,now=NOW)['rows'][0]['ai_stage']=='no_symbol_trace'


def test_code_blocker_and_actual_ai_rejection_are_distinct():
    old,trace,q=inputs();q['candidates']=[{'candidate_id':'stocks:ASH','eligible_for_paper_review':False,
        'paper_blockers':['net_reward_below_2r']}]
    r=build(old,trace,q,now=NOW)['rows'][0]
    assert r['ai_stage']=='code_evidence_or_risk_blocked' and r['blockers']==['net_reward_below_2r']
    d={'schema_version':'paper-final-decision-v1','candidate_id':'stocks:ASH','verdict':'NO_ACTION','blockers':['specialist_veto']}
    assert build(old,trace,q,now=NOW,decision=d)['rows'][0]['ai_stage']=='ai_review_no_action'
