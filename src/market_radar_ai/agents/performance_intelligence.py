"""Offline, reproducible projections of existing paper evidence. No network writes.

The source journals and frozen replay engines remain authoritative. Missing
observations, costs and receipts are not fabricated, and alternatives never pool.
"""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import UTC, timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path
from random import Random
import sqlite3
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from .candidate_packages import canonical, digest
from .comparison_live import LiveComparison, event_id
from .event_archive import EventArchive
from . import execution_research as execution_engine
from .paper_comparison import aware
from .paper_verdict import paper_attempt_id
from .research_views import comparison_rows
from .trade_evaluation import fill_quote_quality

D = Decimal
ZONE = ZoneInfo('Europe/Dublin')
PROTOCOL_PATH = Path(__file__).resolve().parents[3] / 'config/research/performance-holdout-20261118.json'
HOLDOUT_ID = '025d8783383052c5e3edcbfe94138fc2ef26404951a717137fdff382c8b8a0d0'


def number(value):
    if isinstance(value, bool):
        raise ValueError('boolean_not_performance_amount')
    result = D(str(value))
    if not result.is_finite() or abs(result) > D('1e15'):
        raise ValueError('invalid_performance_amount')
    return result


def amount(value):
    return format(value, 'f') if value is not None else None


def local_day(at):
    return aware(at).astimezone(ZONE).date().isoformat()


def read_archive(path):
    archive = EventArchive()
    try:
        with gzip.open(path, 'rt') as source:
            for line in source:
                archive.append(json.loads(line))
        return archive
    except BaseException:
        archive.close()
        raise


def validate_projection(events, *, now, protocol):
    """Replay the existing domain validator; no live client or append interface."""
    partitions = {}
    # Disk indexes bound memory independently of quote-history length. The
    # original event bytes and their digest never change.
    events.db.execute('CREATE INDEX IF NOT EXISTS performance_day_sequence ON events(json_extract(raw,\'$.day\'),seq)')
    events.db.execute('DROP TABLE IF EXISTS temp.performance_identities')
    events.db.execute('CREATE TEMP TABLE performance_identities(id TEXT PRIMARY KEY,seq INTEGER UNIQUE,sha TEXT)')
    protocol_id = digest(protocol)
    for event in events.ordered():
        identity = event['event_id']
        duplicate = events.db.execute('SELECT sha FROM performance_identities WHERE id=?', (identity,)).fetchone()
        if duplicate:
            if duplicate[0] != digest(event):
                raise ValueError('conflicting_source_duplicate')
            raise ValueError('duplicate_source_event')
        if (event['experiment_id'] != protocol_id or event_id(protocol_id, event) != identity
                or event['day'] != aware(event['occurred_at']).date().isoformat()
                or type(event['seq']) is not int):
            raise ValueError('source_identity_or_sequence')
        if max(aware(event['occurred_at']), aware(event['received_at'])) > now:
            raise ValueError('source_after_report_cutoff')
        try:
            events.db.execute('INSERT INTO performance_identities VALUES(?,?,?)', (identity, event['seq'], digest(event)))
        except sqlite3.IntegrityError:
            raise ValueError('source_identity_or_sequence') from None
        day = event['day']; receipt = aware(event['received_at']).astimezone(UTC).isoformat()
        if day not in partitions:
            partitions[day] = {'day': day, 'events': 0, 'first_receipt': receipt, 'last_receipt': receipt,
                'error_polls_max': None, 'maximum_poll_gap_seconds': None, 'full_session_coverage_established': False}
        stats = partitions[day]; stats['events'] += 1
        stats['first_receipt'] = min(stats['first_receipt'], receipt)
        stats['last_receipt'] = max(stats['last_receipt'], receipt)
        if event['kind'] == 'report':
            health = json.loads(event['payload_json']).get('observation_health') or {}
            for target, source in [('error_polls_max', 'error_polls'), ('maximum_poll_gap_seconds', 'maximum_poll_gap_seconds')]:
                stats[target] = max(stats[target] or 0, health.get(source, 0))
    events.db.execute('DROP TABLE temp.performance_identities')
    events.db.commit()
    rows, quality, sessions = [], {}, []
    for day, stats in sorted(partitions.items()):
        def day_events(after=-1, limit=-1):
            for (raw,) in events.db.execute('SELECT raw FROM events WHERE json_extract(raw,\'$.day\')=? '
                                            'AND seq>? ORDER BY seq LIMIT ?', (day, after, limit)):
                yield json.loads(raw)

        class ReadOnly:
            def read(self, experiment, requested_day, after):
                if experiment != protocol_id or requested_day != day:
                    raise ValueError('projection_partition')
                page = list(day_events(after, 1000))
                return {'events': page, 'next': page[-1]['seq'] if page else after}

        with TemporaryDirectory() as root:
            worker = LiveComparison(Path(root), client=ReadOnly(), day=day,
                                    clock=lambda: now, protocol=protocol)
            worker.sync()
            report = worker.store.report(now=now)
            daily = comparison_rows(report)
        rows.extend(daily)
        quality[day] = {arm: fill_quote_quality(daily, day_events(), arm)
                        for arm in ('code_only', 'ai_reviewed')}
        sessions.append({**stats, 'cohorts': len(daily)})
    return rows, quality, sessions


def closed_metrics(rows):
    """Closed paper trades only. No fills and unknown exits never become zero P/L."""
    states = Counter(r['state'] for r in rows)
    closed = [r for r in rows if r['state'] == 'closed']
    for r in closed:
        if r.get('pnl') is None or not r.get('entry_at') or not r.get('exit_at'):
            raise ValueError('incomplete_closed_trade')
        if aware(r['exit_at']) < aware(r['entry_at']):
            raise ValueError('exit_before_entry')
    pnls = [number(r['pnl']) for r in closed]
    wins = sum((p for p in pnls if p > 0), D(0))
    losses = -sum((p for p in pnls if p < 0), D(0))
    by_exit = defaultdict(Decimal)
    for r in closed:
        by_exit[aware(r['exit_at'])] += number(r['pnl'])
    equity = peak = drawdown = D(0)
    for _, change in sorted(by_exit.items()):
        equity += change
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    known_fees = all(r.get('fee_total') is not None for r in closed)
    return {'considered': len(rows), 'states': dict(sorted(states.items())),
        'closed': len(closed), 'wins': sum(p > 0 for p in pnls),
        'losses': sum(p < 0 for p in pnls), 'breakeven': sum(p == 0 for p in pnls),
        'closed_net_pnl_eur': amount(sum(pnls, D(0))) if closed else None,
        'expectancy_per_closed_trade_eur': amount(sum(pnls, D(0)) / len(closed)) if closed else None,
        'profit_factor': amount(wins / losses) if losses else None,
        'profit_factor_status': 'defined' if losses else 'no_losses_observed' if closed else 'no_closed_trades',
        'win_rate': amount(D(sum(p > 0 for p in pnls)) / len(closed)) if closed else None,
        'closed_fees_eur': amount(sum((number(r['fee_total']) for r in closed), D(0)))
            if closed and known_fees else None,
        'realized_drawdown_eur': amount(drawdown) if closed else None,
        'drawdown_scope': 'closed_realized_only_not_mark_to_market',
        'unknown_or_open_outcomes': sum(states[s] for s in ('unresolved', 'open', 'open_simulation')),
        'profitability_established': False}


def day_bootstrap(rows, *, seed=20261118, samples=2000):
    """Exploratory day-cluster interval, not an independence/edge guarantee."""
    days = defaultdict(list)
    for r in rows:
        if r['state'] == 'closed':
            days[local_day(r['exit_at'])].append(number(r['pnl']))
    groups = [days[day] for day in sorted(days)]
    if len(groups) < 2:
        return {'days_with_closes': len(groups), 'lower_95_eur': None, 'upper_95_eur': None,
                'reason': 'fewer_than_two_exit_days'}
    rng = Random(seed)
    values = []
    for _ in range(samples):
        draw = [groups[rng.randrange(len(groups))] for _ in groups]
        values.append(sum((sum(g, D(0)) for g in draw), D(0)) / sum(map(len, draw)))
    values.sort()
    return {'days_with_closes': len(groups), 'lower_95_eur': amount(values[int(.025 * samples)]),
        'upper_95_eur': amount(values[min(samples - 1, int(.975 * samples))]),
        'samples': samples, 'seed': seed, 'reason': 'exploratory_dependent_day_blocks'}


class ContextIndex:
    """Validate each context once; causal joins are logarithmic, not repeated hashes."""
    def __init__(self, contexts):
        from ..market_data.market_context import EXPERIMENT as CONTEXT_ID
        valid = []
        for item in contexts:
            report = item['report']
            if digest(report) != item['sha256']:
                raise ValueError('context_digest_mismatch')
            available = aware(item['available_at'])
            if (report.get('protocol_id') != CONTEXT_ID or report.get('dataset_kind') != 'forward'
                    or report.get('trade_authorized') is not False or report.get('reason') is not None
                    or available < aware(report['as_of']) or not report.get('cutoff_at')
                    or aware(report['cutoff_at']) > available):
                continue
            spy = next((b for b in report['benchmarks'] if b['symbol'] == 'SPY'), None)
            if spy and spy.get('return_pct') is not None and spy['observed_buckets'] == report['expected_buckets']:
                valid.append((available, number(spy['return_pct']), item['sha256']))
        self.values = sorted(valid)
        self.clocks = [r[0] for r in self.values]


def causal_regime(contexts, at):
    """Only a prior available SPY observation; no candidate-price proxy or backfill."""
    now = aware(at)
    index = contexts if isinstance(contexts, ContextIndex) else ContextIndex(contexts)
    position = bisect_right(index.clocks, now) - 1
    if position < 0 or now - index.clocks[position] > timedelta(minutes=15):
        return {'label': 'unknown', 'source_sha256': None}
    available, change, source = index.values[position]
    return {'label': 'up' if change >= D('.3') else 'down' if change <= D('-.3') else 'flat',
            'source_sha256': source, 'available_at': available.isoformat(), 'spy_session_return_pct': amount(change)}


def cost_coverage(rows):
    attempted = [r for r in rows if r['review_started_at'] or r['decision_at'] or
                 (r['ai_cost'] and (number(r['ai_cost']['settled_microeur']) > 0 or
                                   number(r['ai_cost'].get('held_microeur', 0)) > 0))]
    incomplete = [r['setup_id'] for r in attempted if not r['ai_cost'] or not r['ai_cost']['complete']]
    known = sum((number(r['ai_cost']['settled_microeur']) / 1000000
                 for r in rows if r['ai_cost']), D(0))
    return {'attempted_reviews': len(attempted), 'not_attempted': len(rows) - len(attempted),
        'incomplete_attempts': incomplete, 'recorded_estimated_eur': amount(known),
        'complete_total_eur': amount(known) if not incomplete else None,
        'basis': 'recorded_model_estimates_not_provider_invoice'}


def paired_ai(rows):
    """First attempted setup per symbol/day; rejected trades are policy-only zeros."""
    seen, selected, paired, excluded = set(), [], [], Counter()
    for row in sorted(rows, key=lambda r: (r['review_started_at'] or r['enrolled_at'], r['setup_id'])):
        if not row['review_started_at']:
            continue
        unit = (row['candidate_id'], local_day(row['review_started_at']))
        if unit in seen:
            continue
        seen.add(unit)
        selected.append(row['setup_id'])
        code, ai = (row['arms'][a] for a in ('code_only', 'ai_reviewed'))
        cost = row['ai_cost']
        if code['state'] != 'closed' or ai['state'] not in ('closed', 'no_action'):
            excluded['outcome_not_comparable'] += 1
        elif not cost or not cost['complete']:
            excluded['model_cost_incomplete'] += 1
        else:
            baseline = number(code['outcome']['net_pnl_eur'])
            treatment = number(ai['outcome']['net_pnl_eur']) if ai['state'] == 'closed' else D(0)
            paired.append({'setup_id': row['setup_id'], 'candidate_id': row['candidate_id'],
                'baseline_net_eur': amount(baseline), 'ai_policy_net_eur': amount(treatment),
                'ai_cost_eur': amount(number(cost['settled_microeur']) / 1000000),
                'delta_after_ai_cost_eur': amount(treatment - baseline - number(cost['settled_microeur']) / 1000000)})
    return {'selected_before_outcome': len(selected), 'matched': len(paired),
        'excluded': dict(excluded), 'pairs': paired,
        'paired_delta_eur': amount(sum((number(r['delta_after_ai_cost_eur']) for r in paired), D(0))) if paired else None,
        'causal_improvement_established': False,
        'note': 'Coverage-selected descriptive policy pairs, not trade expectancy or randomized AI effect. Missing pairs are not zero. Delays and selection differ.'}


def enrich_book(book, metadata, contexts):
    rows = []
    for original in book['rows']:
        row = dict(original)
        meta = metadata.get(row['setup_id'], {})
        row['strategy_id'] = meta.get('strategy_id', 'unknown')
        row['regime'] = causal_regime(contexts, row['at'])
        row['decision_day_dublin'] = local_day(row['at'])
        row['decision_hour_dublin'] = aware(row['at']).astimezone(ZONE).strftime('%H:00')
        rows.append(row)
    grouped = {}
    for dimension in ('strategy_id', 'decision_day_dublin', 'decision_hour_dublin', 'regime'):
        groups = defaultdict(list)
        for row in rows:
            key = row['regime']['label'] if dimension == 'regime' else row[dimension]
            groups[key].append(row)
        grouped[dimension] = {k: closed_metrics(v) for k, v in sorted(groups.items())}
    return {**book, 'rows': rows, 'metrics': closed_metrics(rows),
            'uncertainty': day_bootstrap(rows), 'by_condition': grouped}


def regime_policy_pairs(rows, protocol):
    """Fixed secondary policy experiment; zero means no allocation, never a fill."""
    selected = set(); groups = {}
    start = aware(protocol['validation_start'])
    for row in sorted(rows, key=lambda r: (aware(r['at']), r['setup_id'])):
        if not row['candidate_id'].startswith('stocks:'):
            continue
        unit = row['candidate_id'], local_day(row['at'])
        if unit in selected:
            continue
        selected.add(unit)
        phase = 'holdout' if aware(row['at']) >= start else 'training_diagnostic'
        result = groups.setdefault(phase, {'selected_before_outcome': 0, 'unknown_context': 0,
            'missing_closed_outcome': 0, 'pairs': []})
        result['selected_before_outcome'] += 1
        regime = row['regime']['label']
        if regime == 'unknown':
            result['unknown_context'] += 1; continue
        if row['state'] != 'closed':
            result['missing_closed_outcome'] += 1; continue
        baseline = number(row['pnl']); filtered = baseline if regime == 'up' else D(0)
        result['pairs'].append({'setup_id': row['setup_id'], 'regime': regime,
            'baseline_net_eur': amount(baseline), 'up_only_policy_eur': amount(filtered),
            'no_action_policy_eur': '0', 'up_only_minus_baseline_eur': amount(filtered - baseline)})
    for result in groups.values():
        pairs = result['pairs']; result['matched_closed'] = len(pairs)
        result['delta_eur'] = amount(sum((number(p['up_only_minus_baseline_eur']) for p in pairs), D(0))) if pairs else None
    return {'protocol_id': digest(protocol['secondary_regime_experiment']), 'phases': groups,
        'causal_improvement_established': False, 'trade_authorized': False,
        'note': 'Same observed independent setups/plans/costs; first enrolment per stock/day. '
                'Up-only selection uses prior available SPY context. Unknown context or outcomes remain excluded with counts. '
                'No-action zeros are allocation-policy comparisons, not zero-profit trades. No portfolio or significance claim.'}


def prospective_gate(book, protocol, *, costs_verified, coverage_complete, as_of):
    start = aware(protocol['validation_start'])
    rows = [r for r in book['rows'] if aware(r['at']) >= start]
    metrics = closed_metrics(rows)
    interval = day_bootstrap(rows, seed=protocol['bootstrap_seed'])
    blockers = []
    if aware(as_of) < start:
        blockers.append('validation_not_started')
    if metrics['closed'] < protocol['minimum_closed_trades']:
        blockers.append('insufficient_closed_sample')
    if interval['days_with_closes'] < protocol['minimum_exit_days']:
        blockers.append('insufficient_independent_sessions')
    if not costs_verified:
        blockers.append('broker_costs_unverified')
    if not coverage_complete:
        blockers.append('end_to_end_coverage_unverified')
    if any(r['state'] in ('open', 'unresolved') for r in book['rows']):
        blockers.append('open_or_unresolved_exposure')
    if interval['lower_95_eur'] is None or number(interval['lower_95_eur']) <= 0:
        blockers.append('positive_net_expectancy_not_supported')
    return {'status': 'blocked' if blockers else 'eligible_for_independent_review',
        'blockers': blockers, 'protocol_id': digest(protocol), 'validation_start': protocol['validation_start'],
        'metrics': metrics, 'uncertainty': interval, 'trade_authorized': False,
        'automatic_promotion': False, 'profitability_claim': None}


def build(events, execution, *, contexts=(), manual=None):
    now = aware(execution['as_of'])
    contexts = ContextIndex(contexts)
    if (execution.get('source_protocol_id') != execution_engine.SOURCE_PROTOCOL_ID
            or execution.get('protocol_id') != execution_engine.EXPERIMENT
            or execution.get('dataset_kind') != 'forward' or execution.get('trade_authorized') is not False
            or execution['source_sha256'] != events.source_digest() or execution['source_events'] != len(events)):
        raise ValueError('execution_source_binding')
    rows, quality, sessions = validate_projection(events, now=now, protocol=execution_engine.SOURCE_PROTOCOL)
    originals, reviews = {}, {}
    for e in events:
        if e['kind'] in ('enrol', 'review'):
            payload = json.loads(e['payload_json'])
            packet = payload['packet']
            body = packet['packet']
            key = paper_attempt_id(packet, now=aware(body['assembled_at']))
            if e['kind'] == 'enrol':
                originals[key] = packet
            else:
                reviews[key] = payload
    clocks = {c['setup_id']: c for c in (manual or {}).get('clocks', [])
              if aware(c['recorded_at']) <= now}
    for r in rows:
        packet = originals[r['setup_id']]
        plan = packet['packet']['plan']
        r.update(packet_id=packet['packet_id'], original_plan=plan)
        reviewed = reviews.get(r['setup_id'])
        r['review_packet_id'] = reviewed['packet']['packet_id'] if reviewed else None
        fx = number(plan['fx_rate'])
        r['native_prices'] = {'currency': plan['native_currency'], **{
            key: amount(number(plan[key + '_eur']) / fx) for key in ('entry', 'stop', 'target')}}
        eligible = r['arms']['ai_reviewed']['plan'] is not None and r['candidate_id'].startswith('stocks:')
        clock = clocks.get(r['setup_id'])
        if clock:
            from .manual_portfolio import bind
            if not reviewed:
                raise ValueError('alert_without_source_review')
            # Review refreshes can legitimately change packet/plan hashes.
            # Bind the acknowledgement to the exact approved packet, while
            # preserving the original enrolment under the stable setup identity.
            bind(clock, reviewed)
        r['alert_acknowledgement'] = {'state': 'acknowledged_not_device_receipt' if clock else
            'not_applicable' if not eligible else 'before_clock_instrumentation' if local_day(r['enrolled_at']) < '2026-11-16'
            else 'unresolved_missing_clock' if manual else 'clock_export_unavailable', 'clock': clock}
    ledger = []
    replayed = execution_engine.replay(events, now=now, ledger_output=ledger)
    if replayed != execution:
        raise ValueError('frozen_execution_replay_mismatch')
    if replayed['source_cohorts'] != len(rows):
        raise ValueError('execution_lifecycle_cohort_mismatch')
    metadata = {r['setup_id']: r for r in rows}
    books = [enrich_book(b, metadata, contexts) for b in ledger]
    independent = []
    for arm in ('code_only', 'ai_reviewed'):
        values = []
        for row in rows:
            a = row['arms'][arm]; outcome = a['outcome'] or {}; plan = a['plan']
            values.append({'setup_id': row['setup_id'], 'candidate_id': row['candidate_id'],
                'state': a['state'], 'reason': outcome.get('reason', a['state']),
                'at': row['decision_at'] if arm == 'ai_reviewed' and row['decision_at'] else row['enrolled_at'],
                'entry_at': outcome.get('entry_at'), 'exit_at': outcome.get('exit_at'),
                'pnl': outcome.get('net_pnl_eur'),
                'fee_total': plan['assumed_round_trip_cost_eur'] if plan and a['state'] == 'closed' else None})
        independent.append(enrich_book({'profile': 'original_flat40_independent', 'arm': arm, 'rows': values,
            'allocation_scope': 'independent_setups_not_a_capital_constrained_portfolio'}, metadata, contexts))
    costs = cost_coverage(rows)
    for book in books:
        net = book['metrics']['closed_net_pnl_eur']
        book['metrics']['net_after_recorded_ai_cost_eur'] = (amount(number(net) - number(costs['complete_total_eur']))
            if book['arm'] == 'ai_reviewed' and net is not None and costs['complete_total_eur'] is not None else
            net if book['arm'] == 'code_only' else None)
    exceptions = [{'setup_id': r['setup_id'], 'candidate_id': r['candidate_id'], 'kind': 'unresolved_outcome',
        'book': b['profile'] + ':' + b['arm'], 'reason': r['reason'], 'reserved_capital_eur': r['capital']}
        for b in books for r in b['rows'] if r['state'] == 'unresolved']
    exceptions += [{'setup_id': key, 'kind': 'review_cost_unsettled'} for key in costs['incomplete_attempts']]
    exceptions += [{'setup_id': r['setup_id'], 'candidate_id': r['candidate_id'], 'kind': 'approved_alert_clock_missing'}
                   for r in rows if r['alert_acknowledgement']['state'] == 'unresolved_missing_clock']
    exceptions += [{'setup_id': r['setup_id'], 'candidate_id': r['candidate_id'],
        'kind': 'independent_outcome_unresolved', 'arm': b['arm'], 'reason': r['reason']}
        for b in independent for r in b['rows'] if r['state'] == 'unresolved']
    report = {'schema_version': 'performance-intelligence-v1', 'dataset_kind': 'historical_analysis', 'as_of': now.isoformat(),
        'as_of_dublin': now.astimezone(ZONE).isoformat(), 'source_sha256': events.source_digest(),
        'source_protocol_id': execution['source_protocol_id'], 'execution_protocol_id': execution['protocol_id'],
        'source_events': len(events), 'cohorts': len(rows), 'sessions': sessions,
        'archive_capacity': {'source_bytes': events.size_bytes, 'maximum_bytes': events.max_bytes,
            'maximum_events': events.max_events, 'attention_required':
                events.size_bytes >= events.max_bytes * .7 or len(events) >= events.max_events * .7},
        'source_kind_counts': dict(Counter(e['kind'] for e in events)), 'ai_costs': costs,
        'books': [{k: v for k, v in b.items() if k != 'rows'} for b in books],
        'independent_setups': [{k: v for k, v in b.items() if k != 'rows'} for b in independent],
        'paired_ai_policy': paired_ai(rows), 'fill_quote_quality': quality,
        'reconciliation_exceptions': exceptions, 'upstream_candidate_history_complete': False,
        'manual': manual, 'model_calls': 0, 'trade_authorized': False,
        'limitations': ['Closed realized P/L only; unobserved exits remain unresolved.',
            'Alternative portfolios are not additive; instrument fills are reference simulations.',
            'Broker fees/currency route remain unverified; net values use frozen cost assumptions.',
            'Missing market context stays unknown; later context is never joined backwards.',
            'Source enrolment excludes upstream rejections; capture evidence is indexed separately.',
            'A minimum sample and bootstrap interval cannot by themselves prove a durable edge.']}
    protocol = json.loads(PROTOCOL_PATH.read_text())
    if digest(protocol) != HOLDOUT_ID:
        raise ValueError('declared_holdout_changed_requires_new_protocol')
    report['holdout_protocol'] = protocol
    report['secondary_regime_experiment'] = regime_policy_pairs(independent[0]['rows'], protocol)
    report['prospective_validation'] = {'status': 'blocked', 'blockers': ['manual_primary_evidence_missing'],
        'protocol_id': digest(protocol), 'profitability_claim': None, 'trade_authorized': False}
    if manual:
        primary = next(b for b in manual['books'] if b['scenario'] == protocol['primary_scenario'])
        report['prospective_validation'] = prospective_gate(primary, protocol,
            costs_verified=manual['costs_verified'], coverage_complete=False, as_of=manual['as_of'])
        report['manual'] = {**manual, 'books': [{k: v for k, v in b.items() if k != 'rows'} for b in manual['books']]}
    return report, rows, books + independent


def manual_evidence(directory):
    """Reproduce the existing manual ledger byte-for-byte before using metrics."""
    from . import manual_portfolio
    from .manual_alert_evidence import EXPERIMENT as CLOCK_ID, PROFILE_PATH, validate_clock
    from .paper_comparison import GUARDED_PROTOCOL
    directory = Path(directory)
    report = json.loads((directory / 'report.json').read_text())
    if report.get('dataset_kind') != 'forward' or report.get('trade_authorized') is not False:
        raise ValueError('manual_forward_evidence_required')
    cutoff = aware(report['evaluated_through'])
    if aware(report['as_of']) < cutoff:
        raise ValueError('manual_generation_before_evaluation')
    with read_archive(directory / 'source-events.jsonl.gz') as events, EventArchive() as comparison:
        if report['source_sha256'] != events.source_digest() or report['source_events'] != len(events):
            raise ValueError('manual_source_hash_mismatch')
        clocks = []
        for e in events:
            if e['experiment_id'] == CLOCK_ID:
                clocks.append(validate_clock(json.loads(e['payload_json'])))
            else:
                comparison.append(e)
        validate_projection(comparison, now=cutoff, protocol=GUARDED_PROTOCOL)
        ledgers = []
        actual = manual_portfolio.replay(events, now=cutoff,
            profile=json.loads(PROFILE_PATH.read_text()), ledger_output=ledgers)
        # The producer deliberately stamps publication time after the replay.
        # Outcomes remain bound to evaluated_through, never to that later clock.
        actual.update(as_of=report['as_of'], evaluation_day=aware(report['as_of']).date().isoformat())
        if actual != report:
            raise ValueError('manual_frozen_replay_mismatch')
        with gzip.open(directory / 'ledger.json.gz', 'rt') as f:
            saved = json.load(f)
        if saved != ledgers or digest(saved) != report['ledger_sha256']:
            raise ValueError('manual_ledger_mismatch')
    return {'as_of': cutoff.isoformat(), 'published_at': report['as_of'], 'protocol_id': report['protocol_id'],
        'source_sha256': report['source_sha256'], 'primary_scenario': report['primary_scenario'],
        'costs_verified': report['costs_verified'], 'clocks': clocks,
        'books': [{'scenario': b['scenario'], 'rows': list(b['rows'].values()),
            'metrics': closed_metrics(list(b['rows'].values())),
            'uncertainty': day_bootstrap(list(b['rows'].values()))} for b in ledgers]}


def write_projection(path, events, report, rows, books):
    """Disposable SQLite index with the exact source export plus derived views."""
    path = Path(path)
    if path.exists():
        raise ValueError('preserve_existing_performance_projection')
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        events.db.commit()
        events.db.backup(db)
        db.execute('CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT INTO metadata VALUES(?,?)', ('report', canonical(report)))
        db.execute('CREATE TABLE setups(setup_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, '
                   'strategy_id TEXT NOT NULL, day TEXT NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE INDEX candidate_history ON setups(candidate_id,day)')
        for r in rows:
            db.execute('INSERT INTO setups VALUES(?,?,?,?,?)', (r['setup_id'], r['candidate_id'],
                r['strategy_id'], local_day(r['enrolled_at']), canonical(r)))
        db.execute('CREATE TABLE portfolios(profile TEXT,arm TEXT,setup_id TEXT,state TEXT,payload TEXT,'
                   'PRIMARY KEY(profile,arm,setup_id))')
        for b in books:
            for r in b['rows']:
                db.execute('INSERT INTO portfolios VALUES(?,?,?,?,?)',
                    (b['profile'], b['arm'], r['setup_id'], r['state'], canonical(r)))
        db.execute('CREATE TABLE exceptions(kind TEXT,setup_id TEXT,payload TEXT)')
        for r in report['reconciliation_exceptions']:
            db.execute('INSERT INTO exceptions VALUES(?,?,?)', (r['kind'], r['setup_id'], canonical(r)))


def markdown(report):
    def eur(value):
        return 'unknown' if value is None else f'€{number(value):.4f}'
    lines = [f"# Paper performance evidence — {report['as_of_dublin']}", '',
        f"{report['source_events']:,} validated events; {report['cohorts']:,} setups. "
        'Frozen replays reproduced exactly. No profitable edge established.', '',
        '| Cost scenario | Arm | Considered | Closed | Net EUR | Expectancy EUR | Profit factor | Realized drawdown EUR | Unknown/open |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for b in report['books']:
        m = b['metrics']
        lines.append(f"| {b['profile']} | {b['arm']} | {m['considered']} | {m['closed']} | "
            f"{eur(m['closed_net_pnl_eur'])} | {eur(m['expectancy_per_closed_trade_eur'])} | "
            f"{m['profit_factor'] or m['profit_factor_status']} | {eur(m['realized_drawdown_eur'])} | {m['unknown_or_open_outcomes']} |")
    costs = report['ai_costs']
    lines += ['', '## Original independent setup outcomes', '',
        'These allocations overlap and are not a shared €1,000 portfolio. Costs use the original flat assumption.', '']
    for b in report['independent_setups']:
        m = b['metrics']
        lines.append(f"- {b['arm']}: {m['closed']} closed, net {eur(m['closed_net_pnl_eur'])}, "
                     f"{m['unknown_or_open_outcomes']} unknown/open outcomes.")
    lines += ['', f"Recorded AI estimates: {eur(costs['recorded_estimated_eur'])}; "
        f"{costs['attempted_reviews']} attempted reviews, {len(costs['incomplete_attempts'])} unsettled, "
        f"{costs['not_attempted']} unattempted. These costs are separate from the trading totals above.", '',
        f"Reconciliation exceptions: {len(report['reconciliation_exceptions'])}. Full setup, rejection, "
        'entry, exit, stop/target and unresolved records are indexed in performance.sqlite.', '',
        '## Prospective evidence gate', '',
        'Status: ' + report['prospective_validation']['status'] + '. ' +
        ', '.join(report['prospective_validation']['blockers']) + '.', '',
        'The primary manual scenario stays EUR conversion with a 300-second response; faster alternatives are sensitivities. '
        'No automatic trading promotion is possible.', '', '## Limits', '']
    lines += ['- ' + x for x in report['limitations']]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution', type=Path, required=True, help='Directory containing report.json and source-events.jsonl.gz')
    parser.add_argument('--manual', type=Path)
    parser.add_argument('--contexts', type=Path, help='JSON list of report, sha256 and proven available_at')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('fresh_output_directory_required')
    execution = json.loads((args.execution / 'report.json').read_text())
    manual = manual_evidence(args.manual) if args.manual else None
    contexts = json.loads(args.contexts.read_text()) if args.contexts else []
    with read_archive(args.execution / 'source-events.jsonl.gz') as events:
        report, rows, books = build(events, execution, contexts=contexts, manual=manual)
        args.output.mkdir(parents=True)
        write_projection(args.output / 'performance.sqlite', events, report, rows, books)
        (args.output / 'performance.json').write_text(json.dumps(report, indent=2) + '\n')
        (args.output / 'performance.md').write_text(markdown(report))
    print(canonical({'state': 'historical_performance_created', 'cohorts': report['cohorts'],
        'exceptions': len(report['reconciliation_exceptions']), 'model_calls': 0, 'trade_authorized': False}))


if __name__ == '__main__':
    main()

