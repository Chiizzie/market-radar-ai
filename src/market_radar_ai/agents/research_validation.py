"""Offline event-time validation diagnostics; no fitting, returns or promotion rule."""
from collections import Counter, defaultdict
from copy import deepcopy
import json
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field

from .knowledge_cases import Strict
from .paper_comparison import aware
from .strategy_knowledge import validate as validate_library


class Label(Strict):
    event_id: str = Field(min_length=1, max_length=150)
    group_id: str = Field(min_length=1, max_length=150)
    partition: str = Field(min_length=1, max_length=300)
    signal_at: AwareDatetime
    label_end: AwareDatetime
    known_at: AwareDatetime


def _day(at):
    return at.astimezone(ZoneInfo('America/New_York')).date()


def chronological_folds(rows, *, as_of, min_train_sessions=3, test_sessions=1, gap_sessions=1):
    """Expanding past-only splits; event-label and receipt clocks purge training.

    A gap counts observed session dates, not inferred exchange trading days. The
    minimum is a split configuration, never a statistical sufficiency threshold.
    """
    if len(rows) > 10000:
        raise ValueError('validation_capacity')
    for value, minimum in ((min_train_sessions, 1), (test_sessions, 1), (gap_sessions, 0)):
        if type(value) is not int or value < minimum:
            raise ValueError('invalid_split_configuration')
    at = aware(as_of)
    labels = [Label.model_validate(r) for r in rows]
    if len({r.event_id for r in labels}) != len(labels):
        raise ValueError('duplicate_validation_event')
    groups = defaultdict(set)
    for r in labels:
        if not r.signal_at <= r.label_end <= r.known_at <= at:
            raise ValueError('invalid_validation_clock')
        groups[(r.partition, r.group_id)].add(_day(r.signal_at))
    if any(len(days) != 1 for days in groups.values()):
        raise ValueError('group_crosses_session_boundary')
    partitions = defaultdict(list)
    for r in labels:
        partitions[r.partition].append(r)
    reports = []
    for partition, items in sorted(partitions.items()):
        items.sort(key=lambda r: (r.signal_at, r.event_id))
        days = sorted({_day(r.signal_at) for r in items})
        folds = []
        for offset in range(min_train_sessions + gap_sessions, len(days) - test_sessions + 1, test_sessions):
            test_days = set(days[offset:offset + test_sessions])
            training_days = set(days[:offset - gap_sessions])
            test = [r for r in items if _day(r.signal_at) in test_days]
            start = min(r.signal_at for r in test)
            test_groups = {r.group_id for r in test}
            candidates = [r for r in items if _day(r.signal_at) in training_days]
            train = [r for r in candidates if r.label_end < start and r.known_at < start
                     and r.group_id not in test_groups]
            folds.append({'test_start': start.isoformat(), 'train_ids': [r.event_id for r in train],
                          'test_ids': [r.event_id for r in test],
                          'purged_ids': [r.event_id for r in candidates if r not in train],
                          'gap_dates': [d.isoformat() for d in days[offset-gap_sessions:offset]],
                          'state': 'prepared' if len({_day(r.signal_at) for r in train}) >= min_train_sessions else 'insufficient_available_training'})
        reports.append({'partition': partition, 'session_dates': [d.isoformat() for d in days],
                        'labels': len(items), 'folds': folds,
                        'state': 'prepared' if any(f['state'] == 'prepared' for f in folds) else 'insufficient_independent_history'})
    return {'schema_version': 'chronological-validation-audit-v1', 'partitions': reports,
            'split_configuration': {'min_train_sessions': min_train_sessions, 'test_sessions': test_sessions, 'gap_sessions': gap_sessions},
            'note': 'Prepared folds are not performance evidence or proof of independent observations.',
            'performance_claim': None, 'trade_authorized': False}


def audit_library(library):
    validate_library(library)
    grouped = defaultdict(list)
    labels = []
    for c in library['cases']:
        partition = ':'.join((c['strategy_id'], c['source_protocol_id'], c['source_policy']))
        grouped[partition].append(c)
        if c['code_only']['state'] == 'closed':
            labels.append({'event_id': c['case_id'], 'group_id': c['candidate_id'] + ':' + _day(aware(c['enrolled_at'])).isoformat(),
                           'partition': partition, 'signal_at': c['enrolled_at'],
                           # Exact exits are not in the compact library; use a conservative upper bound.
                           'label_end': c['known_at'], 'known_at': c['known_at']})
    partitions = []
    for partition, cases in sorted(grouped.items()):
        partitions.append({'partition': partition, 'setups': len(cases),
                           'session_dates': sorted({_day(aware(c['enrolled_at'])).isoformat() for c in cases}),
                           'symbol_session_groups': len({(c['candidate_id'], _day(aware(c['enrolled_at']))) for c in cases}),
                           'outcome_states': dict(Counter(c['code_only']['state'] for c in cases))})
    return {'library_id': library['library_id'], 'setups': len(library['cases']),
            'session_dates': sorted({_day(aware(c['enrolled_at'])).isoformat() for c in library['cases']}),
            'partitions': partitions,
            'validation': chronological_folds(labels, as_of=library['training_cutoff']),
            'limitations': ['No performance inference from two development sessions.',
                            'Unfilled and unresolved setups are excluded from closed-outcome labels, not converted to zero returns.',
                            'Known-at timestamps conservatively bound label end; exact exit clocks require original journals.',
                            'Symbol/session counts describe clustering, not independent bets.'],
            'performance_claim': None}


def audit_future_dependence(extractor, rows, cutoffs):
    """Compare a supplied LOCAL extractor on full data versus available prefixes.

    Contract: extractor(rows, as_of) returns one JSON-serializable historical
    snapshot. Passing tested cutoffs is not a general proof of no lookahead.
    """
    if len(rows) > 10000 or not 1 <= len(cutoffs) <= 20:
        raise ValueError('prefix_audit_capacity')
    seen = set()
    for row in rows:
        if row['event_id'] in seen or aware(row['available_at']) < aware(row['event_at']):
            raise ValueError('invalid_prefix_event')
        seen.add(row['event_id'])
    results = []
    for cutoff in cutoffs:
        at = aware(cutoff)
        prefix = [r for r in rows if aware(r['event_at']) <= at and aware(r['available_at']) <= at]
        if not prefix or len(prefix) == len(rows):
            results.append({'as_of': at.isoformat(), 'state': 'not_exercised'})
            continue
        before = deepcopy(prefix); full = deepcopy(rows)
        try:
            left = extractor(before, at); right = extractor(full, at)
            # Reject non-finite or unsupported output instead of hiding NaN equality.
            left_json = json.dumps(left, sort_keys=True, allow_nan=False)
            right_json = json.dumps(right, sort_keys=True, allow_nan=False)
            mutated = before != prefix or full != rows
            state = 'failed' if mutated or left_json != right_json else 'passed_tested_cutoff'
            results.append({'as_of': at.isoformat(), 'state': state,
                            'reason': 'input_mutation' if mutated else 'future_dependence' if left_json != right_json else None})
        except Exception as exc:
            results.append({'as_of': at.isoformat(), 'state': 'failed', 'reason': type(exc).__name__})
    return {'schema_version': 'future-dependence-audit-v1', 'checks': results,
            'passed_tested_cutoffs': sum(r['state'] == 'passed_tested_cutoff' for r in results),
            'failed_cutoffs': sum(r['state'] == 'failed' for r in results),
            'limitation': 'Only exercised inputs and cutoffs are tested; missing triggers, joins or revisions can conceal leakage.',
            'performance_claim': None, 'trade_authorized': False}
