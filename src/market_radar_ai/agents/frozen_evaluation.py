"""Full-detail offline replay of already frozen strategy and entry experiments."""
from bisect import bisect_right
from collections import defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .candidate_packages import digest
from .comparison_live import event_id
from .paper_comparison import aware
from .performance_intelligence import closed_metrics, day_bootstrap


def evaluate(files, kind):
    from .strategy_experiment_live import StrategyExperiment, paired_results
    from .entry_confirmation_live import EntryExperiment
    from .entry_confirmation import build_report, outcomes, coverage
    original = json.loads(files['report.json'])
    now = aware(original['as_of'])
    if original['trade_authorized'] is not False or original['dataset_kind'] != 'forward':
        raise ValueError('frozen_forward_evidence_required')
    events = [json.loads(line) for line in files['events.jsonl'].splitlines() if line.strip()]
    seqs = [e['seq'] for e in events]
    if any(type(s) is not int for s in seqs) or seqs != sorted(set(seqs)):
        raise ValueError('frozen_event_order')
    for e in events:
        if (e['experiment_id'] != original['protocol_id'] or e['day'] != original['evaluation_day']
                or event_id(e['experiment_id'], e) != e['event_id']
                or max(aware(e['occurred_at']), aware(e['received_at'])) > now):
            raise ValueError('frozen_event_identity_or_clock')

    class ReadOnly:
        def read(self, experiment, day, after):
            if experiment != original['protocol_id'] or day != original['evaluation_day']:
                raise ValueError('frozen_partition')
            start = bisect_right(seqs, after); page = events[start:start + 1000]
            return {'events': page, 'next': page[-1]['seq'] if page else after}

    with TemporaryDirectory() as root:
        worker_type = StrategyExperiment if kind == 'strategy' else EntryExperiment if kind == 'entry' else None
        if worker_type is None:
            raise ValueError('unsupported_frozen_experiment')
        worker = worker_type(Path(root), client=ReadOnly(), day=original['evaluation_day'], clock=lambda: now)
        worker.sync()
        actual = worker.report() if kind == 'strategy' else build_report(worker, now)
        keys = ('protocol_id', 'cohort_count', 'source_event_count', 'source_events_sha256',
                'variants' if kind == 'strategy' else 'arms')
        if any(actual[k] != original[k] for k in keys):
            raise ValueError('frozen_experiment_replay_mismatch')
        if kind == 'entry' and actual['comparison'] != original['comparison']:
            raise ValueError('frozen_entry_comparison_mismatch')
        full = {name: [] for name in actual['variants' if kind == 'strategy' else 'arms']}
        if kind == 'strategy':
            for key, variants in worker.outcomes(now).items():
                for name, row in variants.items():
                    full[name].append(normalize(key, worker.cohorts[key], row))
            pairs = paired_results(worker, now)['pairs']
        else:
            quotes = defaultdict(list)
            for q in worker.quotes:
                quotes[q['candidate_id']].append(q)
            for key, cohort in worker.cohorts.items():
                pair = outcomes(cohort, quotes[cohort['candidate_id']], now)
                quality = coverage(quotes[cohort['candidate_id']], pair)
                for name, row in pair.items():
                    full[name].append({**normalize(key, cohort, row), 'paired_coverage': quality})
            pairs = actual['comparison']
        return {'schema_version': 'frozen-experiment-evaluation-v1', 'kind': kind,
            'protocol_id': original['protocol_id'], 'evaluation_day': original['evaluation_day'],
            'as_of': original['as_of'], 'source_sha256': original['source_events_sha256'],
            'original_report_sha256': digest(original), 'cohorts': len(worker.cohorts),
            'arms': {name: {'metrics': closed_metrics(rows), 'uncertainty': day_bootstrap(rows), 'rows': rows}
                     for name, rows in sorted(full.items())},
            'comparisons': pairs, 'model_calls': 0, 'trade_authorized': False,
            'scope': 'independent_allocations_not_a_portfolio', 'edge_established': False,
            'note': 'All frozen arms retained. Closed-pair subsets may be selected by coverage and are not significance tests.'}


def normalize(key, cohort, row):
    return {'setup_id': key, 'candidate_id': cohort['candidate_id'], 'at': cohort['enrolled_at'],
        'state': row['state'], 'reason': row.get('reason'), 'entry_at': row.get('entry_at'),
        'exit_at': row.get('exit_at'), 'pnl': row.get('net_pnl_eur'),
        'fee_total': row.get('fee_eur'), 'original_outcome': row}


def summarize_latest(snapshots):
    """One latest snapshot per protocol/day, never sum repeated cumulative runs."""
    latest = {}
    for snapshot in snapshots:
        key = snapshot['protocol_id'], snapshot['evaluation_day']
        if key in latest and aware(snapshot['as_of']) == aware(latest[key]['as_of']) and digest(snapshot) != digest(latest[key]):
            raise ValueError('conflicting_frozen_snapshot_clock')
        if key not in latest or aware(snapshot['as_of']) > aware(latest[key]['as_of']):
            latest[key] = snapshot
    protocols = defaultdict(lambda: defaultdict(list))
    for (protocol, day), snapshot in sorted(latest.items()):
        for arm, values in snapshot['arms'].items():
            protocols[protocol][arm].extend(values['rows'])
    return {'snapshots': [{k: v for k, v in s.items() if k != 'arms'} for s in latest.values()],
        'protocols': {p: {a: {'metrics': closed_metrics(rows), 'uncertainty': day_bootstrap(rows)}
                           for a, rows in arms.items()} for p, arms in protocols.items()},
        'profitability_claim': None,
        'note': 'Historical summaries of fixed alternatives; commissioning and validation dates remain attached to each snapshot. No strategy selection or automatic rule change.'}
