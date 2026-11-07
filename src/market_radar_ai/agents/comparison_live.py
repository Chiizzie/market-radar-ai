"""Durable prospective experiment. Signed append-only evidence; no model/orders/alerts.

SQLite is a disposable projection. PostgreSQL events are authoritative, with a
bounded signed transport and a lossless JSONL export for independent recovery.
"""
import hashlib
import hmac
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from .candidate_packages import canonical, digest
from .paper_comparison import ComparisonStore, PROTOCOL, aware, validate_packet
from .paper_outcomes import Quote
from .paper_verdict import paper_attempt_id

ENDPOINT = 'https://pixel-perfect-replay-32614.lovable.app/api/public/research-events'
KINDS = {'enrol', 'begin', 'quote', 'review', 'cost', 'report', 'audit'}


def event_id(experiment, event):
    return hashlib.sha256(f"{experiment}.{event['kind']}.{event['occurred_at']}.{event['payload_json']}".encode()).hexdigest()


class EventClient:
    def __init__(self, secret, *, clock=lambda: datetime.now(UTC), session=None):
        if not isinstance(secret, str) or len(secret) < 32:
            raise ValueError('comparison_storage_not_configured')
        self.secret = secret
        self.clock = clock
        self.session = session or requests.Session()

    def request(self, body):
        raw = canonical({'version': 'research-events-v1', **body})
        if len(raw.encode()) > 2 * 1024 * 1024:
            raise ValueError('comparison_transport_capacity')
        timestamp = str(int(self.clock().timestamp()))
        signature = hmac.new(self.secret.encode(), f'{timestamp}.{raw}'.encode(), hashlib.sha256).hexdigest()
        try:
            response = self.session.post(ENDPOINT, data=raw.encode(), timeout=(5, 12),
                headers={'Content-Type': 'application/json', 'X-Timestamp': timestamp,
                         'X-Signature': 'sha256=' + signature}, allow_redirects=False)
            if response.status_code != 200 or len(response.content) > 2 * 1024 * 1024:
                raise ValueError('comparison_storage_unavailable')
            result = response.json()
            if result.get('ok') is not True:
                raise ValueError('comparison_storage_unavailable')
            return result
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise RuntimeError('comparison_storage_unavailable') from None

    def append(self, experiment, events):
        if not events:
            return
        days = {e['occurred_at'][:10] for e in events}
        if len(days) != 1:
            raise ValueError('comparison_single_day_batch_required')
        result = self.request({'action': 'append', 'experiment_id': experiment,
                               'day': days.pop(), 'events': events})
        if result['event_ids'] != [event_id(experiment, e) for e in events]:
            raise ValueError('comparison_receipt_mismatch')

    def read(self, experiment, day, after):
        return self.request({'action': 'read', 'experiment_id': experiment, 'day': day, 'after': after})


def envelope(kind, payload, now):
    return {'kind': kind, 'occurred_at': aware(now).isoformat(),
            'payload_json': canonical({**payload, 'dataset_kind': 'forward', 'trade_authorized': False})}


class LiveComparison:
    """One projection per process, serialized across the inline observer/reviewer.

    Failed durable writes never count as recorded observations. Replay is only
    from authenticated immutable events; synthetic exercises use ComparisonStore.
    """
    def __init__(self, directory, *, client, observer=None, clock=lambda: datetime.now(UTC), day=None):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / 'comparison.sqlite'
        if path.exists():
            raise ValueError('fresh_comparison_projection_required')
        self.store = ComparisonStore(path)
        self.client, self.observer, self.clock = client, observer, clock
        self.day = day or aware(clock()).date().isoformat()
        self.experiment = digest(PROTOCOL)
        self.cursor = 0
        self.seen = set()
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.health = {'polls': 0, 'quotes_received': 0, 'error_polls': 0,
                       'capacity_deferred': 0, 'maximum_poll_gap_seconds': 0,
                       'target_interval_seconds': 5, 'model_calls': 0}
        self.last_poll = None

    def apply(self, event):
        if event['event_id'] in self.seen:
            return
        if (event['experiment_id'] != self.experiment or event['day'] != self.day
                or event['kind'] not in KINDS or event_id(self.experiment, event) != event['event_id']):
            raise ValueError('invalid_comparison_event')
        self.apply_payload(self.store, event)
        with (self.root / 'comparison-events.jsonl').open('a') as out:
            out.write(canonical(event) + '\n')
        self.seen.add(event['event_id'])

    @staticmethod
    def apply_payload(store, event):
        p = json.loads(event['payload_json'])
        if p['dataset_kind'] != 'forward' or p['trade_authorized'] is not False:
            raise ValueError('forward_comparison_only')
        now = aware(event['occurred_at'])
        kind = event['kind']
        if kind == 'enrol': store.enrol(p['packet'], now=now)
        elif kind == 'begin': store.begin_review(p['packet'], now=now)
        elif kind == 'quote': store.observe(p['candidate_id'], Quote.model_validate(p['quote']),
                                               source=p['source'], received_at=p['received_at'])
        elif kind == 'review': store.record_review(p['packet'], p['audit'], p['decision'], now=now)
        elif kind == 'cost': store.record_cost(p['key'], settled_microeur=p['settled_microeur'],
                              held_microeur=p['held_microeur'], complete=p['complete'], now=now)

    def sync(self):
        with self.lock:
            for _ in range(2000):
                page = self.client.read(self.experiment, self.day, self.cursor)
                if not page['events']:
                    return
                for event in page['events']:
                    if type(event['seq']) is not int or event['seq'] <= self.cursor:
                        raise ValueError('comparison_event_order')
                    self.apply(event)
                    self.cursor = event['seq']
                if page['next'] != self.cursor:
                    raise ValueError('comparison_cursor_mismatch')
            raise ValueError('comparison_sync_capacity')

    def push(self, kind, payload, now):
        with self.lock:
            event = envelope(kind, payload, now)
            # Validate against a disposable snapshot before making evidence
            # immutable. A malformed review cannot poison durable replay.
            if kind not in ('report', 'audit'):
                with TemporaryDirectory() as scratch:
                    path = Path(scratch)/'validation.sqlite'
                    self.store.backup(path)
                    self.apply_payload(ComparisonStore(path), event)
            self.client.append(self.experiment, [event])
            self.sync()

    def enrol(self, packet, *, now):
        with self.lock:
            validate_packet(packet, now)
            key = paper_attempt_id(packet, now=aware(packet['packet']['assembled_at']))
            with sqlite3.connect(self.store.path) as db:
                exists = db.execute('SELECT 1 FROM comparison_cohort WHERE id=?', (key,)).fetchone()
            if not exists:
                self.push('enrol', {'packet': packet}, now)
            return key

    def begin_review(self, packet, *, now):
        self.push('begin', {'packet': packet}, now)

    def enrol_many(self, packets, *, now):
        """Bounded batch admission avoids one network round trip per candidate."""
        with self.lock:
            with sqlite3.connect(self.store.path) as db:
                existing = {r[0] for r in db.execute('SELECT id FROM comparison_cohort')}
            batches, batch, size = [], [], 0
            for packet in packets:
                validate_packet(packet, now)
                key = paper_attempt_id(packet, now=aware(packet['packet']['assembled_at']))
                if key in existing: continue
                existing.add(key)
                event = envelope('enrol', {'packet': packet}, now)
                length = len(canonical(event).encode())
                if size + length > 1_500_000 or len(batch) >= 50:
                    batches.append(batch); batch, size = [], 0
                batch.append(event); size += length
            if batch: batches.append(batch)
            for batch in batches:
                self.client.append(self.experiment, batch)
            self.sync()

    def record_review(self, packet, audit, decision, *, now):
        self.push('review', {'packet': packet, 'audit': audit, 'decision': decision}, now)

    def reconcile_cost(self, packet, ledger_state, *, now):
        from .github_budget import validate_state
        from .paper_verdict import STAGES
        entries = validate_state(ledger_state)['entries']
        rows = [entries.get('paper-final-v1:' + packet['packet_id'] + ':' + s) for s in STAGES]
        self.push('cost', {'key': paper_attempt_id(packet, now=aware(packet['packet']['assembled_at'])),
                  'settled_microeur': sum(r['actual'] for r in rows if r and r['actual'] is not None),
                  'held_microeur': sum(r['reserved'] for r in rows if r and r['actual'] is None),
                  'complete': all(r and r['actual'] is not None for r in rows)}, now)

    def poll(self):
        with self.lock:
            self.sync()
            now = self.clock()
            if self.last_poll is not None:
                self.health['maximum_poll_gap_seconds'] = max(self.health['maximum_poll_gap_seconds'],
                                                             (now - self.last_poll).total_seconds())
            self.last_poll = now
            report = self.store.report(now=now)
            active = {r['setup_id'] for r in report['rows'] if any(r[arm]['state'] in
                ('watching', 'open_simulation') for arm in ('code_only', 'ai_reviewed'))}
            decisions = []
            with sqlite3.connect(self.store.path) as db:
                for key, raw in db.execute('SELECT id,payload FROM comparison_cohort ORDER BY id'):
                    if key not in active: continue
                    cohort = json.loads(raw); packet = cohort['packet']; body = packet['packet']
                    decisions.append({'candidate_id': body['candidate_id'], 'packet_id': packet['packet_id'],
                        'evaluated_at': cohort['enrolled_at'], 'plan': body['plan']})
            selected, counts = [], {'stocks': set(), 'crypto': set()}
            for d in decisions:
                market = d['candidate_id'].split(':')[0]; limit = 40 if market == 'stocks' else 30
                if d['candidate_id'] not in counts[market] and len(counts[market]) >= limit:
                    self.health['capacity_deferred'] += 1
                    continue
                counts[market].add(d['candidate_id']); selected.append(d)
            observations, failures = self.observer.fetch(selected) if selected else ([], [])
            received = self.clock()
            by_packet = {d['packet_id']: d['candidate_id'] for d in selected}
            events, seen = [], set()
            for observation in observations:
                candidate = by_packet[observation['packet_id']]
                if candidate in seen: continue
                seen.add(candidate)
                quote = Quote.model_validate(observation['quote'])
                if not 0 <= (received - quote.observed_at).total_seconds() <= 60:
                    failures.append('stale_comparison_quote'); continue
                events.append(envelope('quote', {'candidate_id': candidate,
                    'quote': quote.model_dump(mode='json'), 'source': observation['source'],
                    'received_at': received.isoformat()}, received))
            self.client.append(self.experiment, events)
            self.sync()
            self.health['polls'] += 1
            self.health['quotes_received'] += len(events)
            self.health['error_polls'] += bool(failures)
            self.health['last_success_at'] = received.isoformat()
            return self.health

    def start_observing(self):
        # The first durable quote attempt completes before model access. Lack of
        # a market quote is disclosed; loss of durable storage fails closed.
        self.poll()
        def work():
            while not self.stop.wait(5):
                try: self.poll()
                except (RuntimeError, ValueError, KeyError, TypeError):
                    self.health['error_polls'] += 1
        self.thread = threading.Thread(target=work, name='paper-comparison-observer', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=45)
        if self.thread and self.thread.is_alive():
            raise RuntimeError('comparison_observer_did_not_stop')
        with self.lock:
            self.sync()
            report = self.store.report(now=self.clock())
            report['observation_health'] = self.health
            report['evaluation_day'] = self.day
            (self.root / 'comparison-report.json').write_text(json.dumps(report, indent=2) + '\n')
            (self.root / 'comparison-health.json').write_text(json.dumps(self.health, indent=2) + '\n')
            # Reports have a bounded summary; detailed immutable events remain the
            # recoverable source. Never truncate a cohort and call it complete.
            from .research_views import append_publication, comparison_rows
            append_publication(self.client,self.experiment,report,comparison_rows(report),clock=self.clock)
            self.sync()
            return report


def restore_events(source, destination, *, client, day):
    restored = LiveComparison(destination, client=client, day=day)
    with Path(source).open() as handle:
        for line in handle:
            restored.apply(json.loads(line))
    return restored.store


def main():
    import argparse, os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--day')
    args = parser.parse_args()
    projection = LiveComparison(args.output, client=EventClient(os.environ.get('REVIEW_INGEST_SECRET')), day=args.day)
    projection.sync()
    report = projection.close()
    print(json.dumps({'state': 'durable_comparison_exported', 'cohort_count': report['cohort_count'],
                      'model_calls': 0, 'trade_authorized': False}))


if __name__ == '__main__': main()
