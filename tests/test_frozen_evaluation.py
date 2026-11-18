from copy import deepcopy
from datetime import timedelta
import json

import pytest

from market_radar_ai.agents.frozen_evaluation import evaluate, summarize_latest
from market_radar_ai.agents.strategy_experiment_live import StrategyExperiment
from test_strategy_experiment import Events, NOW, fixture


def test_full_strategy_projection_reproduces_original_without_public_row_limit(tmp_path):
    events = Events(); now = [NOW]
    worker = StrategyExperiment(tmp_path / 'original', client=events, clock=lambda: now[0])
    worker.enrol([fixture()], capture_sha='b' * 64)
    now[0] += timedelta(minutes=4)
    original = worker.report()
    files = {'events.jsonl': worker.journal.read_bytes(), 'report.json': json.dumps(original).encode()}
    report = evaluate(files, 'strategy')
    assert report['cohorts'] == 1 and len(report['arms']) == 10
    assert all(v['metrics']['closed_net_pnl_eur'] is None for v in report['arms'].values())
    assert report['trade_authorized'] is False and not report['edge_established']
    bad = deepcopy(original); bad['variants']['rolling_structural_usd']['closed'] = 100
    with pytest.raises(ValueError, match='frozen_experiment_replay_mismatch'):
        evaluate({**files, 'report.json': json.dumps(bad).encode()}, 'strategy')
    rows = files['events.jsonl'].splitlines()
    with pytest.raises(ValueError, match='frozen_event_order'):
        evaluate({**files, 'events.jsonl': b'\n'.join(rows + rows)}, 'strategy')


def test_repeated_cumulative_reports_never_double_count():
    row = {'state': 'closed', 'pnl': '2', 'fee_total': '.1', 'entry_at': '2026-11-19T15:00:00Z',
           'exit_at': '2026-11-19T16:00:00Z'}
    a = {'protocol_id': 'a', 'evaluation_day': '2026-11-19', 'as_of': '2026-11-19T16:01:00Z',
         'arms': {'baseline': {'rows': [row]}}}
    b = {**a, 'as_of': '2026-11-19T17:00:00Z'}
    report = summarize_latest([a, b, a])
    assert report['protocols']['a']['baseline']['metrics']['closed'] == 1
    assert report['protocols']['a']['baseline']['metrics']['closed_net_pnl_eur'] == '2'
    assert report['profitability_claim'] is None


def test_entry_replays_complete_paired_coverage_and_costs(tmp_path):
    from types import SimpleNamespace
    from test_entry_confirmation import fixture as entry_fixture, NOW as ENTRY_NOW, quote
    from market_radar_ai.agents.entry_confirmation import build_report, VARIANT
    from market_radar_ai.agents.entry_confirmation_live import EntryExperiment
    from decimal import Decimal
    client = Events(); clock = [ENTRY_NOW]
    worker = EntryExperiment(tmp_path / 'entry', client=client, clock=lambda: clock[0])
    worker.enrol([entry_fixture()], capture_sha='a' * 64)
    c = next(iter(worker.cohorts.values()))
    for seconds, price in [(1, c['variants'][VARIANT]['plan']['entry_usd']),
                           (6, c['variants'][VARIANT]['plan']['target_usd'])]:
        clock[0] = ENTRY_NOW + timedelta(seconds=seconds)
        q = quote(c, Decimal(price), seconds=seconds); q.pop('durable_received_at')
        worker.poll(SimpleNamespace(fetch=lambda selected: ([q], [])))
    original = build_report(worker, clock[0])
    result = evaluate({'report.json': json.dumps(original).encode(), 'events.jsonl': worker.journal.read_bytes()}, 'entry')
    assert result['comparisons'] == original['comparison']
    assert result['arms']['ask_trigger']['metrics']['closed'] == 1
    assert result['arms']['ask_trigger']['metrics']['closed_fees_eur'] is not None
    assert result['arms']['bid_confirmed']['metrics']['closed'] == 1


def test_conflicting_same_clock_reports_are_not_arbitrarily_selected():
    a = {'protocol_id': 'a', 'evaluation_day': '2026-11-19', 'as_of': '2026-11-19T16:01:00Z', 'arms': {}}
    with pytest.raises(ValueError, match='conflicting_frozen_snapshot_clock'):
        summarize_latest([a, {**a, 'cohorts': 99}])
