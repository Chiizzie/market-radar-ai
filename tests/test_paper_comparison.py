import json
import sqlite3
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_github_budget import MemoryStore
from test_paper_verdict import NOW, fixture

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.github_budget import GitHubSpendingLedger, initial_state
from market_radar_ai.agents.openai_pilot import OpenAIPilot
from market_radar_ai.agents.paper_comparison import (
    PROTOCOL,
    ComparisonStore,
    aware,
    cohort_snapshot,
)
from market_radar_ai.agents.paper_outcomes import Quote
from market_radar_ai.agents.paper_verdict import STAGES, finalize, run_pipeline


def setup(tmp_path, monkeypatch, *, verdict='approve', delay=0):
    _, packet, audit, _ = fixture(monkeypatch)
    store = ComparisonStore(tmp_path / 'comparison.sqlite', dataset_kind='synthetic')
    key = store.enrol(packet, now=NOW)
    store.begin_review(packet, now=NOW)
    at = NOW + timedelta(seconds=delay)
    audit['completed_at'] = at.isoformat()
    if verdict == 'reject':
        audit['reviews'][3]['verdict'] = 'REJECT'
    decision = finalize(packet, audit, {}, None, now=at)
    store.record_review(packet, audit, decision, now=at)
    return store, key, packet, audit, decision


def observe(store, packet, seconds, price, *, received=None):
    at = NOW + timedelta(seconds=seconds)
    store.observe(packet['packet']['candidate_id'], Quote(observed_at=at, bid=price, ask=price),
                  source='synthetic:quote', received_at=received or at)


def test_same_observations_compare_both_arms_and_deduct_actual_ai_cost(tmp_path, monkeypatch):
    store, key, packet, _, decision = setup(tmp_path, monkeypatch)
    plan = decision['plan']
    observe(store, packet, 5, plan['entry_eur'])
    observe(store, packet, 10, plan['target_eur'])
    store.record_cost(key, settled_microeur=12500, held_microeur=0, complete=True, now=NOW)
    report = store.report(now=NOW + timedelta(seconds=11))
    assert report['code_only']['closed'] == report['ai_reviewed']['closed'] == 1
    assert report['code_only']['closed_net_pnl_eur'] == report['ai_reviewed']['closed_net_pnl_eur']
    assert Decimal(report['matched_observed_pairs'][0]['delta_before_ai_cost_eur']) == 0
    assert Decimal(report['matched_observed_pairs'][0]['delta_after_ai_cost_eur']) == Decimal('-.0125')
    assert report['dataset_kind'] == 'synthetic' and not report['trade_authorized']
    assert report['model_calls_by_report'] == 0
    assert Decimal(report['complete_cohort_delta_after_ai_cost_eur']) == Decimal('-.0125')


def test_rejection_stays_a_counterfactual_and_not_an_approved_position(tmp_path, monkeypatch):
    store, key, packet, _, decision = setup(tmp_path, monkeypatch, verdict='reject')
    plan = packet['packet']['plan']
    observe(store, packet, 5, plan['entry_eur'])
    observe(store, packet, 10, Decimal(plan['stop_eur']) - Decimal('.01'))
    store.record_cost(key, settled_microeur=10000, held_microeur=0, complete=True, now=NOW)
    report = store.report(now=NOW + timedelta(seconds=11))
    row = report['rows'][0]
    assert row['rejected_counterfactual_only']
    assert row['ai_reviewed'] == {'state': 'no_action', 'outcome': None}
    assert report['ai_reviewed']['closed'] == report['ai_reviewed']['wins'] == 0
    assert report['ai_reviewed']['closed_net_pnl_eur'] is None
    assert Decimal(report['matched_observed_pairs'][0]['delta_after_ai_cost_eur']) > 0
    from market_radar_ai.agents.paper_tracking import PaperTracker
    with pytest.raises(ValueError, match='approved_paper_decision_required'):
        PaperTracker(tmp_path / 'production-like.sqlite').register(decision)


def test_ai_cannot_use_entries_that_happened_during_review(tmp_path, monkeypatch):
    store, _, packet, _, _ = setup(tmp_path, monkeypatch, delay=10)
    plan = packet['packet']['plan']
    observe(store, packet, 2, plan['entry_eur'])
    observe(store, packet, 3, plan['target_eur'])
    report = store.report(now=NOW + timedelta(minutes=2))
    assert report['code_only']['closed'] == 1
    assert report['ai_reviewed']['states'] == {'not_filled': 1}
    assert report['approved_entries_missed_or_unobserved'] == 1
    assert report['matched_observed_pairs'] == []
    assert report['ai_costs']['complete_total_eur'] is None
    assert report['excluded_pair_count'] == 1
    assert report['complete_cohort_delta_after_ai_cost_eur'] is None


def test_late_receipt_never_backdates_a_scheduled_exit(tmp_path, monkeypatch):
    store, _, packet, _, decision = setup(tmp_path, monkeypatch)
    plan = decision['plan']
    observe(store, packet, 5, plan['entry_eur'])
    end = aware(plan['exit_by'])
    seconds = (end - NOW).total_seconds() - 5
    observe(store, packet, seconds, plan['entry_eur'], received=end + timedelta(seconds=1))
    report = store.report(now=end + timedelta(seconds=2))
    for arm in ('code_only', 'ai_reviewed'):
        assert report[arm]['states'] == {'unresolved': 1}
        assert report[arm]['closed_net_pnl_eur'] is None
    assert report['matched_observed_pairs'] == []


def test_scheduled_exit_costs_and_missing_observations_are_not_wins(tmp_path, monkeypatch):
    store, _, packet, _, decision = setup(tmp_path, monkeypatch)
    plan = decision['plan']
    empty = store.report(now=NOW + timedelta(minutes=2))
    assert empty['code_only']['closed'] == empty['ai_reviewed']['wins'] == 0
    assert empty['code_only']['closed_net_pnl_eur'] is None
    observe(store, packet, 5, plan['entry_eur'])
    end = aware(plan['exit_by'])
    observe(store, packet, (end - NOW).total_seconds() - 17, plan['entry_eur'])
    report = store.report(now=end)
    assert report['code_only']['losses'] == 1
    assert Decimal(report['code_only']['closed_net_pnl_eur']) == -Decimal(plan['assumed_round_trip_cost_eur'])
    assert report['rows'][0]['code_only']['outcome']['reason'] == 'scheduled_exit'


def test_enrolment_deduplicates_without_rewriting_initial_window(tmp_path, monkeypatch):
    _, packet, _, _ = fixture(monkeypatch)
    store = ComparisonStore(tmp_path / 'comparison.sqlite', dataset_kind='synthetic')
    key = store.enrol(packet, now=NOW)
    assert store.enrol(packet, now=NOW + timedelta(seconds=1)) == key
    report = store.report(now=NOW + timedelta(seconds=2))
    assert report['cohort_count'] == 1 and report['rows'][0]['enrolled_at'] == NOW.isoformat()
    assert report['ai_reviewed']['states'] == {'not_reviewed': 1}
    with pytest.raises(ValueError):
        store.enrol(packet, now=NOW + timedelta(minutes=2))


@pytest.mark.parametrize('fault', ['crossed', 'stale', 'future', 'before_enrolment', 'other_candidate'])
def test_bad_observations_are_rejected(tmp_path, monkeypatch, fault):
    store, _, packet, _, decision = setup(tmp_path, monkeypatch)
    at = NOW + timedelta(seconds=5)
    received = at
    bid = ask = decision['plan']['entry_eur']
    candidate = packet['packet']['candidate_id']
    if fault == 'crossed':
        bid = Decimal(ask) + 1
    if fault == 'stale':
        received += timedelta(seconds=61)
    if fault == 'future':
        at += timedelta(seconds=1)
    if fault == 'before_enrolment':
        at = NOW - timedelta(seconds=1)
    if fault == 'other_candidate':
        candidate = 'stocks:OTHER'
    with pytest.raises(ValueError):
        store.observe(candidate, Quote(observed_at=at, bid=bid, ask=ask),
                      source='synthetic', received_at=received)


def test_quotes_reviews_and_completed_costs_are_immutable(tmp_path, monkeypatch):
    store, key, packet, audit, decision = setup(tmp_path, monkeypatch)
    observe(store, packet, 5, decision['plan']['entry_eur'])
    observe(store, packet, 5, decision['plan']['entry_eur'])
    with pytest.raises(ValueError, match='immutable'):
        observe(store, packet, 5, decision['plan']['target_eur'])
    store.record_review(packet, audit, decision, now=NOW + timedelta(seconds=1))
    changed = deepcopy(audit)
    changed['reviews'][0]['rationale'] = 'Different assessment'
    with pytest.raises(ValueError, match='immutable'):
        store.record_review(packet, changed, decision, now=NOW)
    store.record_cost(key, settled_microeur=1000, held_microeur=0, complete=True, now=NOW)
    with pytest.raises(ValueError, match='cannot_rewrite'):
        store.record_cost(key, settled_microeur=999, held_microeur=0, complete=True, now=NOW)


def test_review_cannot_be_attached_without_prior_registration_of_attempt(tmp_path, monkeypatch):
    _, packet, audit, _ = fixture(monkeypatch)
    decision = finalize(packet, audit, {}, None, now=NOW)
    store = ComparisonStore(tmp_path / 'comparison.sqlite', dataset_kind='synthetic')
    store.enrol(packet, now=NOW)
    with pytest.raises(ValueError, match='prospective_review_start'):
        store.record_review(packet, audit, decision, now=NOW)


def test_partial_costs_and_holds_are_separate_and_unknown_not_zero(tmp_path, monkeypatch):
    store, _, packet, _, _ = setup(tmp_path, monkeypatch)
    state = initial_state()
    prefix = 'paper-final-v1:' + packet['packet_id'] + ':'
    state['entries'][prefix + STAGES[0]] = {'day': NOW.date().isoformat(), 'reserved': 10000,
                                          'actual': 1000, 'usage': None}
    state['entries'][prefix + STAGES[1]] = {'day': NOW.date().isoformat(), 'reserved': 20000,
                                          'actual': None, 'usage': None}
    store.reconcile_cost(packet, state, now=NOW)
    cost = store.report(now=NOW)['ai_costs']
    assert Decimal(cost['settled_estimated_eur']) == Decimal('.001')
    assert Decimal(cost['held_maximum_eur']) == Decimal('.02')
    assert cost['complete_total_eur'] is None and cost['unreconciled_candidates'] == 1
    for stage in STAGES:
        state['entries'][prefix + stage] = {'day': NOW.date().isoformat(), 'reserved': 20000,
                                           'actual': 1000, 'usage': None}
    store.reconcile_cost(packet, state, now=NOW + timedelta(seconds=1))
    assert Decimal(store.report(now=NOW + timedelta(seconds=1))['ai_costs']['complete_total_eur']) == Decimal('.008')
    assert store.report(now=NOW)['ai_costs'] == cost


def test_drawdown_uses_exit_order_and_counts_only_closed_outcomes():
    from market_radar_ai.agents.paper_comparison import metrics
    values = [('2026-11-06T15:00:00+00:00', '10'), ('2026-11-06T15:01:00+00:00', '-4'),
              ('2026-11-06T15:02:00+00:00', '2'), ('2026-11-06T15:03:00+00:00', '-12')]
    arms = [{'state': 'closed', 'outcome': {'exit_at': at, 'net_pnl_eur': value}} for at, value in reversed(values)]
    arms += [{'state': 'unresolved', 'outcome': {'net_pnl_eur': None}}, {'state': 'no_action', 'outcome': None}]
    result = metrics(arms)
    assert result['closed'] == 4 and result['wins'] == result['losses'] == 2
    assert result['closed_net_pnl_eur'] == '-4' and result['realized_closed_drawdown_eur'] == '14'
    assert result['average_gain_eur'] == '6' and result['average_loss_eur'] == '-8'
    assert result['average_closed_pnl_eur'] == '-1'


def test_protocol_synthetic_separation_and_backup_recovery(tmp_path, monkeypatch):
    store, _, packet, _, decision = setup(tmp_path, monkeypatch)
    observe(store, packet, 5, decision['plan']['entry_eur'])
    expected = store.report(now=NOW + timedelta(seconds=6))
    backup = tmp_path / 'backup.sqlite'
    store.backup(backup)
    restored = ComparisonStore(backup, dataset_kind='synthetic')
    assert restored.report(now=NOW + timedelta(seconds=6)) == expected
    with sqlite3.connect(backup) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    with pytest.raises(ValueError, match='dataset_changed'):
        ComparisonStore(backup, dataset_kind='forward')
    with pytest.raises(ValueError, match='unsupported_comparison_protocol'):
        ComparisonStore(backup, dataset_kind='synthetic', protocol={**PROTOCOL, 'version': 'changed'})
    with pytest.raises(ValueError, match='preserve_existing'):
        store.backup(backup)


def test_snapshot_hash_and_protocol_are_independent_of_mutation(tmp_path, monkeypatch):
    _, packet, _, _ = fixture(monkeypatch)
    snapshot = cohort_snapshot([packet], now=NOW)
    body = {k: v for k, v in snapshot.items() if k != 'cohort_sha256'}
    assert digest(body) == snapshot['cohort_sha256']
    snapshot['protocol']['version'] = 'tampered'
    assert PROTOCOL['version'] == 'paper-comparison-v1'


def test_pipeline_freezes_cohort_before_paid_work_and_records_partial_failure(tmp_path, monkeypatch):
    fixture(monkeypatch)
    store = ComparisonStore(tmp_path / 'experiment.sqlite', dataset_kind='synthetic')
    client = OpenAIPilot(api_key='synthetic', ledger=GitHubSpendingLedger(MemoryStore()),
                         eur_per_usd='.9', enabled=True)
    root = tmp_path / 'run'

    def fail(**kwargs):
        snapshot = json.loads((root / 'comparison-cohort.json').read_text())
        assert len(snapshot['packets']) == 1 and not snapshot['observations_started']
        report = store.report(now=NOW)
        assert report['cohort_count'] == 1 and report['ai_reviewed']['states'] == {'review_incomplete': 1}
        raise RuntimeError('synthetic model failure')

    monkeypatch.setattr(client, 'call', fail)
    with pytest.raises(RuntimeError, match='synthetic model failure'):
        run_pipeline({}, None, client=client, root=root, refresh=lambda symbol: ({}, None),
                     deliver=lambda archive: {}, clock=lambda: NOW, enabled=True, comparison=store)
    report = store.report(now=NOW)
    assert report['ai_reviewed']['closed'] == 0 and report['matched_observed_pairs'] == []
    assert report['ai_costs']['complete_total_eur'] is None


def test_full_pipeline_acceptance_can_feed_separate_comparison_store(tmp_path, monkeypatch):
    fixture(monkeypatch)
    store = ComparisonStore(tmp_path / 'experiment.sqlite', dataset_kind='synthetic')
    client = OpenAIPilot(api_key='synthetic', ledger=GitHubSpendingLedger(MemoryStore()),
                         eur_per_usd='.9', enabled=True)
    monkeypatch.setattr(client, 'call', lambda **kwargs: SimpleNamespace(data={
        'verdict': 'APPROVE_PAPER', 'rationale': 'Synthetic test', 'source_ids': ['news:test'], 'concerns': []}))
    result = run_pipeline({}, None, client=client, root=tmp_path / 'run', refresh=lambda symbol: ({}, None),
                          deliver=lambda archive: {'state': 'synthetic'}, clock=lambda: NOW,
                          enabled=True, comparison=store)
    assert result['verdict'] == 'PAPER_WATCH_FOR_ENTRY'
    assert store.report(now=NOW)['ai_reviewed']['states'] == {'watching': 1}
    # Mocked model calls are not represented as real settled provider charges.
    assert store.report(now=NOW)['ai_costs']['complete_total_eur'] is None
