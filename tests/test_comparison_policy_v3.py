import pytest

from test_conditional_policy_v3 import fixture
from market_radar_ai.agents.paper_comparison import ComparisonStore
from market_radar_ai.agents.paper_verdict import finalize
from market_radar_ai.agents.review_policy import team_approval_allowed, CONDITIONAL_CHIEF_POLICY


def prepared(tmp_path):
    document, feed, now, packet, audit = fixture()
    store = ComparisonStore(tmp_path/'comparison.sqlite', dataset_kind='synthetic')
    store.enrol(packet, now=now)
    store.begin_review(packet, now=now)
    return store, document, feed, now, packet, audit


@pytest.mark.parametrize('uncertain_stages', [(1, 3, 4), (4, 6)])
def test_conditional_approval_survives_durable_recording(tmp_path, uncertain_stages):
    # The patterns reproduce BP/DRH's completed chief approvals without copying
    # production evidence or retrospectively publishing their lost decisions.
    store, document, feed, now, packet, audit = prepared(tmp_path)
    for i in uncertain_stages:
        audit['reviews'][i]['verdict'] = 'MORE_EVIDENCE_REQUIRED'
    decision = finalize(packet, audit, document, feed, now=now)
    assert decision['verdict'] == 'PAPER_WATCH_FOR_ENTRY'
    store.record_review(packet, audit, decision, now=now)
    row = store.report(now=now)['rows'][0]
    assert row['ai_reviewed']['state'] == 'watching'
    assert row['decision_at'] == decision['evaluated_at']


@pytest.mark.parametrize('stage', range(8))
def test_no_reviewer_rejection_can_be_recorded_as_approval(tmp_path, stage):
    store, document, feed, now, packet, audit = prepared(tmp_path)
    decision = finalize(packet, audit, document, feed, now=now)
    audit['reviews'][stage]['verdict'] = 'REJECT'
    assert finalize(packet, audit, document, feed, now=now)['verdict'] == 'NO_ACTION'
    with pytest.raises(ValueError, match='invalid_comparison_approval'):
        store.record_review(packet, audit, decision, now=now)


def test_chief_uncertainty_cannot_be_recorded_as_approval(tmp_path):
    store, document, feed, now, packet, audit = prepared(tmp_path)
    decision = finalize(packet, audit, document, feed, now=now)
    audit['reviews'][-1]['verdict'] = 'MORE_EVIDENCE_REQUIRED'
    with pytest.raises(ValueError, match='invalid_comparison_approval'):
        store.record_review(packet, audit, decision, now=now)


@pytest.mark.parametrize('policy', [None, 'paper-specialists-v2-chart-thesis', 'unknown'])
def test_historical_or_unknown_policy_keeps_unanimity(policy):
    verdicts = ['APPROVE_PAPER']*8
    assert team_approval_allowed(verdicts, policy_version=policy)
    verdicts[3] = 'MORE_EVIDENCE_REQUIRED'
    assert not team_approval_allowed(verdicts, policy_version=policy)
    assert team_approval_allowed(verdicts, policy_version=CONDITIONAL_CHIEF_POLICY)


def test_policy_mismatch_cannot_upgrade_a_decision(tmp_path):
    store, document, feed, now, packet, audit = prepared(tmp_path)
    decision = finalize(packet, audit, document, feed, now=now)
    decision.pop('review_policy_version')
    with pytest.raises(ValueError, match='invalid_comparison_review_chain'):
        store.record_review(packet, audit, decision, now=now)


@pytest.mark.parametrize('fault', ['changed_plan', 'expired', 'blockers', 'bad_citation'])
def test_conditional_rule_does_not_bypass_evidence_or_plan_checks(tmp_path, fault):
    store, document, feed, now, packet, audit = prepared(tmp_path)
    audit['reviews'][3]['verdict'] = 'MORE_EVIDENCE_REQUIRED'
    decision = finalize(packet, audit, document, feed, now=now)
    if fault == 'changed_plan': decision['plan']['entry_eur'] = '0'
    if fault == 'expired': decision['plan']['expires_at'] = now.isoformat()
    if fault == 'blockers': decision['blockers'] = ['reference_quote_not_confirmed']
    if fault == 'bad_citation': audit['reviews'][3]['source_ids'] = ['invented']
    with pytest.raises(ValueError): store.record_review(packet, audit, decision, now=now)
