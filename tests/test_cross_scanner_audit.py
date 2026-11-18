from datetime import datetime, UTC, timedelta
import pytest
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


@pytest.mark.parametrize('delivery_state,expected,attempts', [
    (None, 'audit_saved_locally_publication_unconfirmed', 1),
    ('scanner_snapshot_delivery_confirmed', 'audit_saved_locally_publication_unconfirmed', 1),
    ('scanner_snapshot_delivery_unconfirmed', 'audit_saved_locally_publication_deferred', 0),
])
def test_unconfirmed_journal_write_keeps_local_gap_evidence(tmp_path, monkeypatch, delivery_state, expected, attempts):
    import json
    import sys
    from unittest.mock import Mock
    from market_radar_ai.dashboard import cross_scanner_audit as audit
    old, trace, q = inputs()
    trace['symbols'][0].update(discovery_rank=19, technical_status='unusable',
        chart_diagnostics={'category':'gapped_iex_history','missing_internal_intervals':5,'contiguous_tail_bars':8})
    old['generated_at'] = q['evaluated_at'] = datetime.now(UTC).isoformat()
    (tmp_path/'discovery-selection.json').write_text(json.dumps(trace))
    (tmp_path/'qualification.json').write_text(json.dumps(q))
    if delivery_state:
        (tmp_path/'delivery.json').write_text(json.dumps({'state': delivery_state}))
    monkeypatch.setattr(audit,'fetch_original',lambda:old)
    client = Mock()
    client.append.side_effect = RuntimeError('storage_timeout')
    monkeypatch.setattr(audit,'EventClient',lambda _:client)
    monkeypatch.setattr(sys,'argv',['audit','--collection',str(tmp_path)])
    assert audit.main() == 1
    report = json.loads((tmp_path/'cross-scanner-audit.json').read_text())
    status = json.loads((tmp_path/'cross-scanner-status.json').read_text())
    assert report['original_signals'] == status['original_signals'] == 1
    assert status['state'] == expected
    assert client.append.call_count == attempts
    details = status['comparison_details'][0]
    assert details['discovery_rank'] == 19 and details['contiguous_tail_bars'] == 8
    assert details['missing_internal_intervals'] == 5 and details['chart_category'] == 'gapped_iex_history'
    assert audit.comparison_details({**report,'timing_status':'not_comparable'},trace) == []
