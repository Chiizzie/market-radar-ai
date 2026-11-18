"""Accounting, causality and immutable replay regressions; no network calls."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import json
import sqlite3

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.event_archive import EventArchive
from market_radar_ai.agents import execution_research as engine
from market_radar_ai.agents.performance_intelligence import (PROTOCOL_PATH, build, causal_regime,
    closed_metrics, cost_coverage, day_bootstrap, local_day, number, paired_ai,
    prospective_gate, validate_projection, write_projection)
from test_comparison_live import environment
from test_execution_research import enrol, quote, NOW


def trade(net='-2', *, date='2026-11-19', state='closed', hour='15'):
    return {'setup_id': 'test-' + date, 'candidate_id': 'stocks:TEST', 'state': state,
        'pnl': net if state == 'closed' else None, 'fee_total': '.5',
        'at': date + 'T14:00:00+00:00', 'entry_at': date + 'T14:01:00+00:00',
        'exit_at': date + 'T' + hour + ':00:00+00:00' if state == 'closed' else None}


def test_metrics_keep_unknowns_and_costs_and_measure_drawdown_in_exit_order():
    rows = [trade('5', date='2026-11-20'), trade('-4', date='2026-11-21'), trade('-2'),
            trade(state='unresolved'), trade(state='expired')]
    result = closed_metrics(rows)
    assert result['closed'] == 3 and result['unknown_or_open_outcomes'] == 1
    assert result['closed_net_pnl_eur'] == '-1'
    assert D(result['expectancy_per_closed_trade_eur']) == D(-1) / 3
    assert D(result['profit_factor']) == D(5) / 6
    assert result['realized_drawdown_eur'] == '4'
    assert result['closed_fees_eur'] == '1.5'  # P/L already net; fees are not subtracted twice.
    assert closed_metrics([trade(state='expired')])['closed_net_pnl_eur'] is None
    assert closed_metrics([trade('2')])['profit_factor_status'] == 'no_losses_observed'


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', True, '1e30'])
def test_invalid_money_fails_closed(bad):
    with pytest.raises(ValueError):
        number(bad)


def test_closed_without_exit_or_pnl_is_rejected():
    for key in ('pnl', 'exit_at', 'entry_at'):
        row = trade(); row[key] = None
        with pytest.raises(ValueError, match='incomplete_closed_trade'):
            closed_metrics([row])


def test_equal_exit_times_are_one_equity_change_and_dublin_uses_dst():
    a, b = trade('-10'), trade('10')
    assert closed_metrics([a, b])['realized_drawdown_eur'] == '0'
    assert local_day('2026-06-10T23:30:00+00:00') == '2026-06-11'


def test_bootstrap_is_deterministic_clusters_days_and_does_not_fill_missing_days():
    rows = [trade('3'), trade('-2', date='2026-11-20'), trade(state='unresolved')]
    a = day_bootstrap(rows)
    assert a == day_bootstrap(list(reversed(rows)))
    assert a['days_with_closes'] == 2 and a['upper_95_eur'] == '3'
    assert day_bootstrap([trade()])['lower_95_eur'] is None


def context(at='2026-11-19T14:59:00+00:00', available='2026-11-19T15:00:00+00:00'):
    from market_radar_ai.market_data.market_context import EXPERIMENT
    r = {'protocol_id': EXPERIMENT, 'as_of': at, 'cutoff_at': at,
         'trade_authorized': False, 'dataset_kind': 'forward', 'reason': None,
         'expected_buckets': 5, 'benchmarks': [{'symbol': 'SPY', 'return_pct': '-0.5', 'observed_buckets': 5}]}
    return {'report': r, 'available_at': available, 'sha256': digest(r)}


def test_regimes_cannot_use_future_incomplete_stale_or_tampered_context():
    c = context()
    assert causal_regime([c], '2026-11-19T15:01:00Z')['label'] == 'down'
    assert causal_regime([c], '2026-11-19T14:59:30Z')['label'] == 'unknown'
    assert causal_regime([c], '2026-11-19T15:16:00Z')['label'] == 'unknown'
    c['report']['benchmarks'][0]['observed_buckets'] = 4
    with pytest.raises(ValueError, match='context_digest_mismatch'):
        causal_regime([c], '2026-11-19T15:01:00Z')
    c['sha256'] = digest(c['report'])
    assert causal_regime([c], '2026-11-19T15:01:00Z')['label'] == 'unknown'


def test_costs_distinguish_unattempted_from_missing_settlement():
    def row(start, cost):
        return {'setup_id': str(start), 'review_started_at': start, 'decision_at': None, 'ai_cost': cost}
    r = cost_coverage([row(None, None), row('yes', None),
        row('settled', {'complete': True, 'settled_microeur': 200000})])
    assert r['not_attempted'] == 1 and r['incomplete_attempts'] == ['yes']
    assert r['complete_total_eur'] is None and r['recorded_estimated_eur'] == '0.2'


def test_ledger_export_does_not_change_frozen_report_or_protocol():
    events = [enrol(1), quote(2, 100), quote(3, 105, seconds=2)]
    before = digest(engine.PROTOCOL)
    baseline = engine.replay(events, now=NOW + timedelta(minutes=1), dataset_kind='synthetic')
    ledgers = []
    assert engine.replay(events, now=NOW + timedelta(minutes=1), dataset_kind='synthetic', ledger_output=ledgers) == baseline
    assert len(ledgers) == 6 and len(ledgers[0]['rows']) == 1
    assert digest(engine.PROTOCOL) == before


def test_end_to_end_projection_binds_source_and_never_rewrites(tmp_path, monkeypatch):
    worker, packet, _, clock, price, client = environment(tmp_path / 'input', monkeypatch)
    # The shared synthetic fixture predates the real experiment's start.
    monkeypatch.setattr(engine, 'PROTOCOL', {**engine.PROTOCOL, 'since': worker.day})
    monkeypatch.setattr(engine, 'EXPERIMENT', digest(engine.PROTOCOL))
    worker.enrol(packet, now=clock[0]); clock[0] += timedelta(seconds=1); worker.poll()
    price[0] = packet['packet']['plan']['target_eur']; clock[0] += timedelta(seconds=1); worker.poll()
    with EventArchive() as events:
        for event in client.events:
            events.append({**event, 'received_at': event['occurred_at']})
        original_hash = events.source_digest()
        execution = engine.replay(events, now=clock[0])
        report, rows, books = build(events, execution)
        assert report['cohorts'] == 1 and report['trade_authorized'] is False
        assert events.source_digest() == original_hash and report['prospective_validation']['status'] == 'blocked'
        path = tmp_path / 'performance.sqlite'
        write_projection(path, events, report, rows, books)
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT count(*) FROM setups').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM events').fetchone()[0] == len(events)
        with pytest.raises(ValueError, match='preserve_existing'):
            write_projection(path, events, report, rows, books)
        tampered = deepcopy(execution); tampered['source_sha256'] = '0' * 64
        with pytest.raises(ValueError, match='execution_source_binding'):
            build(events, tampered)
        tampered = deepcopy(execution); tampered['books'][0]['closed'] = 99
        with pytest.raises(ValueError, match='frozen_execution_replay_mismatch'):
            build(events, tampered)


def test_future_receipts_duplicate_ids_and_unknown_protocols_fail(tmp_path, monkeypatch):
    worker, packet, _, clock, _, client = environment(tmp_path / 'input', monkeypatch)
    worker.enrol(packet, now=clock[0]); event = {**client.events[0], 'received_at': clock[0].isoformat()}
    for mutation, error in [('future', 'source_after_report_cutoff'), ('duplicate', 'duplicate_source_event'),
                            ('protocol', 'source_identity_or_sequence')]:
        with EventArchive() as archive:
            row = deepcopy(event)
            if mutation == 'future': row['received_at'] = (clock[0] + timedelta(seconds=1)).isoformat()
            if mutation == 'protocol': row['experiment_id'] = '0' * 64
            archive.append(row)
            if mutation == 'duplicate': archive.append(row)
            with pytest.raises(ValueError, match=error):
                validate_projection(archive, now=clock[0], protocol=engine.SOURCE_PROTOCOL)


def test_holdout_excludes_training_and_cannot_hide_unresolved_carryover():
    protocol = json.loads(PROTOCOL_PATH.read_text())
    old = trade('100000', date='2026-11-18')
    result = prospective_gate({'rows': [old, trade('1'), trade(state='unresolved', date='2026-11-17')]},
        protocol, costs_verified=False, coverage_complete=False, as_of='2026-11-20T23:00:00Z')
    assert result['metrics']['closed_net_pnl_eur'] == '1'
    assert 'broker_costs_unverified' in result['blockers']
    assert 'open_or_unresolved_exposure' in result['blockers']
    assert 'end_to_end_coverage_unverified' in result['blockers']
    assert result['trade_authorized'] is False and result['profitability_claim'] is None


def test_paired_policy_uses_first_attempt_before_outcomes_and_retains_missing():
    def r(key, at, state):
        return {'setup_id': key, 'candidate_id': 'stocks:A', 'review_started_at': at, 'enrolled_at': at,
            'ai_cost': {'complete': True, 'settled_microeur': 100000},
            'arms': {'code_only': {'state': state, 'outcome': {'net_pnl_eur': '-2'}},
                     'ai_reviewed': {'state': 'no_action', 'outcome': None}}}
    first = r('first', '2026-11-19T15:00:00Z', 'unresolved')
    later = r('later', '2026-11-19T16:00:00Z', 'closed')
    result = paired_ai([later, first])
    assert result['selected_before_outcome'] == 1 and result['matched'] == 0
    first['arms']['code_only']['state'] = 'closed'
    result = paired_ai([later, first])
    assert result['pairs'][0]['setup_id'] == 'first' and result['paired_delta_eur'] == '1.9'


def test_declared_regime_comparison_separates_training_and_unseen_data():
    from market_radar_ai.agents.performance_intelligence import regime_policy_pairs
    protocol = json.loads(PROTOCOL_PATH.read_text())
    a = {**trade('-2', date='2026-11-18'), 'regime': {'label': 'down'}}
    b = {**trade('5', date='2026-11-19'), 'regime': {'label': 'up'}}
    c = {**trade('99', date='2026-11-20'), 'regime': {'label': 'unknown'}}
    d = {**trade(state='unresolved', date='2026-11-21'), 'regime': {'label': 'down'}}
    result = regime_policy_pairs([a, b, c, d], protocol)
    assert result['phases']['training_diagnostic']['delta_eur'] == '2'
    holdout = result['phases']['holdout']
    assert holdout['matched_closed'] == 1 and holdout['delta_eur'] == '0'
    assert holdout['unknown_context'] == holdout['missing_closed_outcome'] == 1
    assert holdout['pairs'][0]['no_action_policy_eur'] == '0'
    assert result['causal_improvement_established'] is False
