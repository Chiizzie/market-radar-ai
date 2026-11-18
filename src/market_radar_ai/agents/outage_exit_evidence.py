"""Retain deadline quotes for already open stock simulations during a storage outage."""
from datetime import timedelta
import json
import re

from .candidate_packages import canonical, digest
from .observation_policy import wide
from .paper_comparison import aware
from .paper_outcomes import Quote
from ..market_data.providers.alpaca import SYMBOL


def verified(document):
    from .paper_comparison import protocol_for_day
    report = document['report']
    protocol = protocol_for_day(report['day'])
    if (digest(report) != document['sha256'] or report['schema_version'] != 'outage-exit-reference-v1'
            or report['experiment_id'] != digest(protocol) or report['applied_to_ledger'] is not False
            or report['trade_authorized'] is not False or report['model_calls'] != 0
            or report['scope'] != 'code_only_open_in_authenticated_prefix'
            or type(report['source_cursor']) is not int or report['source_cursor'] < 1
            or type(report['polls']) is not int or not 1 <= report['polls'] <= 7
            or type(report['eligible_packets']) is not int or report['eligible_packets'] < 1
            or type(report['failure_count']) is not int or report['failure_count'] < 0
            or not isinstance(report['quotes'],list) or len(report['quotes']) > 40 * report['polls']):
        raise ValueError('invalid_outage_exit_evidence')
    seen = set()
    for row in report['quotes']:
        quote = Quote.model_validate(row['quote'])
        deadline = aware(row['deadline'])
        identity = (row['packet_id'], quote.observed_at)
        if (identity in seen or not re.fullmatch(r'[0-9a-f]{64}', row['packet_id'])
                or not row['candidate_id'].startswith('stocks:') or not SYMBOL.fullmatch(row['candidate_id'][7:])
                or not re.fullmatch(r'alpaca_iex:[0-9a-f]{64}', row['source'])
                or deadline.date().isoformat() != report['day'] or quote.bid > quote.ask
                or not deadline - timedelta(seconds=protocol['exit_window_seconds']) <= quote.observed_at <= aware(row['received_at']) <= deadline
                or row['spread_quality'] != ('wide' if wide(quote) else 'within_guard')):
            raise ValueError('invalid_outage_exit_reference')
        seen.add(identity)
    return report


def upcoming(worker, now, remaining):
    candidates = {}
    window = timedelta(seconds=worker.protocol['exit_window_seconds'])
    with worker.store.connection() as db:
        for key, raw in db.execute('SELECT id,payload FROM comparison_cohort ORDER BY id'):
            cohort = json.loads(raw)
            packet = cohort['packet']
            body = packet['packet']
            deadline = aware(body['plan']['exit_by'])
            if body['candidate_id'].startswith('stocks:') and now <= deadline and deadline - window < now + remaining:
                candidates[key] = {'candidate_id': body['candidate_id'], 'packet_id': packet['packet_id'],
                    'evaluated_at': cohort['enrolled_at'], 'plan': body['plan']}
    if not candidates:
        return []
    opened = {r['setup_id'] for r in worker.store.report(now=now)['rows'] if r['code_only']['state'] == 'open_simulation'}
    return sorted((d for key, d in candidates.items() if key in opened),
                  key=lambda d: (aware(d['plan']['exit_by']), d['packet_id']))


def record(worker, *, clock, monotonic, sleep, end, interval, in_scope):
    """A signed checkpoint is a historical prefix. Its instruments can supply research references only."""
    now = aware(clock())
    remaining = end - monotonic()
    if (worker.health.get('checkpoint_state') != 'restored' or not worker.cursor or remaining <= 0
            or not in_scope(now) or now.date().isoformat() != worker.day):
        return None
    decisions = upcoming(worker, now, timedelta(seconds=remaining))
    if not decisions:
        return None
    window = timedelta(seconds=worker.protocol['exit_window_seconds'])
    path = worker.root / 'outage-exit-evidence.json'
    report = {'schema_version': 'outage-exit-reference-v1', 'day': worker.day, 'experiment_id': worker.experiment,
              'source_cursor': worker.cursor, 'scope': 'code_only_open_in_authenticated_prefix',
              'eligible_packets': len(decisions), 'polls': 0, 'failure_count': 0, 'quotes': [],
              'trade_authorized': False, 'model_calls': 0, 'applied_to_ledger': False}
    seen = set()
    while monotonic() < end and report['polls'] < 7:
        now = aware(clock())
        if not in_scope(now) or now.date().isoformat() != worker.day:
            break
        pending = [d for d in decisions if now <= aware(d['plan']['exit_by'])]
        if not pending:
            break
        wait = (aware(pending[0]['plan']['exit_by']) - window - now).total_seconds()
        if wait > 0:
            sleep(min(wait, max(0, end - monotonic())))
            continue
        selected = [d for d in pending if aware(d['plan']['exit_by']) - window <= now][:40]
        by_packet = {d['packet_id']: d for d in selected}
        started = monotonic()
        observations, failures = worker.observer.fetch(selected)
        received = aware(clock())
        report['polls'] += 1
        report['failure_count'] += len(failures)
        for observation in observations:
            decision = by_packet[observation['packet_id']]
            deadline = aware(decision['plan']['exit_by'])
            quote = Quote.model_validate(observation['quote'])
            identity = (decision['packet_id'], quote.observed_at)
            if (identity in seen or quote.bid > quote.ask or observation['symbol'] != decision['plan']['symbol']
                    or not deadline - window <= quote.observed_at <= received <= deadline):
                continue
            seen.add(identity)
            report['quotes'].append({'packet_id': decision['packet_id'], 'candidate_id': decision['candidate_id'],
                'deadline': deadline.isoformat(), 'received_at': received.isoformat(), 'source': observation['source'],
                'quote': quote.model_dump(mode='json'), 'spread_quality': 'wide' if wide(quote) else 'within_guard'})
        staged = path.with_suffix('.tmp')
        staged.write_text(canonical({'report': report, 'sha256': digest(report)}) + '\n')
        staged.replace(path)
        sleep(min(max(0, end - monotonic()), max(.1, max(5, interval) - (monotonic() - started))))
    return {'polls': report['polls'], 'references': len(report['quotes']), 'failure_count': report['failure_count']}
