"""Read-only export and deterministic replay of frozen signed comparison evidence."""
import argparse
import gzip
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .candidate_packages import canonical, digest
from .comparison_live import EventClient, KINDS, LiveComparison, event_id, restore_event_timestamp
from .knowledge_cases import Case, features, library_summary, outcome, seal_library
from .paper_comparison import ComparisonStore, GUARDED_PROTOCOL, aware, protocol_for_day
from .paper_verdict import paper_attempt_id

TRAINING_CUTOFF = '2026-11-13T21:17:12+00:00'
TRAINING_DAYS = ('2026-11-12', '2026-11-13')


def validate_event(raw, *, day, after):
    experiment = digest(GUARDED_PROTOCOL)
    event = restore_event_timestamp(experiment, raw)
    if (type(event['seq']) is not int or event['seq'] <= after
            or event['experiment_id'] != experiment or event['day'] != day
            or event['kind'] not in KINDS or event_id(experiment, event) != event['event_id']):
        raise ValueError('invalid_knowledge_source_event')
    aware(event['received_at'])  # Mandatory server receipt, not substituted with event time.
    if aware(event['occurred_at']).date().isoformat() != day:
        raise ValueError('invalid_knowledge_source_partition')
    return event


def download_partition(client, *, day, path):
    if protocol_for_day(day) != GUARDED_PROTOCOL:
        raise ValueError('incompatible_source_protocol')
    after = count = 0
    with gzip.open(path, 'wt') as out:
        for _ in range(2000):
            page = client.read(digest(GUARDED_PROTOCOL), day, after)
            if not page['events']:
                return count
            for raw in page['events']:
                event = validate_event(raw, day=day, after=after)
                after = event['seq']
                out.write(canonical(event)+'\n')
                count += 1
                if count > 250000:
                    raise ValueError('knowledge_source_capacity')
            if page['next'] != after:
                raise ValueError('knowledge_source_cursor_mismatch')
    raise ValueError('knowledge_source_page_capacity')


def replay_partition(path, *, day, cutoff, projection):
    cutoff = aware(cutoff)
    store = ComparisonStore(projection, protocol=GUARDED_PROTOCOL)
    after = count = accepted = excluded = excluded_crypto = 0
    source_hash = hashlib.sha256()
    enrol_events = {}
    seen = set()
    with gzip.open(path, 'rb') as source, store.replay_batch():
        for line in source:
            if len(line) > 2_000_000 or count >= 250000:
                raise ValueError('knowledge_source_capacity')
            source_hash.update(line)
            event = validate_event(json.loads(line), day=day, after=after)
            after = event['seq']; count += 1
            if event['event_id'] in seen:
                raise ValueError('duplicate_knowledge_source_event')
            seen.add(event['event_id'])
            if max(aware(event['occurred_at']), aware(event['received_at'])) > cutoff:
                excluded += 1
                continue
            payload = json.loads(event['payload_json'])
            # Local quote receipt is independently checked as well as server receipt.
            if event['kind'] == 'quote' and aware(payload['received_at']) > cutoff:
                excluded += 1
                continue
            LiveComparison.apply_payload(store, event)
            accepted += 1
            if event['kind'] == 'enrol':
                packet = payload['packet']
                key = paper_attempt_id(packet, now=aware(packet['packet']['assembled_at']))
                enrol_events.setdefault(key, event['event_id'])
    report = store.report(now=cutoff)
    with store.connection() as db:
        cohorts = {key:json.loads(payload) for key,payload in
                   db.execute('SELECT id,payload FROM comparison_cohort')}
    cases = []
    for row in report['rows']:
        key = row['setup_id']; packet = cohorts[key]['packet']; body = packet['packet']
        if not row['candidate_id'].startswith('stocks:'):
            excluded_crypto += 1
            continue
        cases.append(Case(setup_id=key, packet_id=packet['packet_id'], enrol_event_id=enrol_events[key],
            candidate_id=row['candidate_id'], enrolled_at=row['enrolled_at'], known_at=cutoff,
            features=features(body), code_only=outcome(row['code_only']), ai_reviewed=outcome(row['ai_reviewed']),
            rejected_counterfactual_only=row['rejected_counterfactual_only']).model_dump(mode='json'))
    manifest = {'day':day, 'protocol_id':digest(GUARDED_PROTOCOL), 'source_event_count':count,
        'accepted_events':accepted, 'after_cutoff_excluded':excluded, 'crypto_cohorts_excluded':excluded_crypto,
        'last_source_seq':after, 'journal_sha256_uncompressed':source_hash.hexdigest(),
        'projection_report_sha256':digest(report), 'stock_cases':len(cases)}
    return cases, manifest


def build(paths, *, cutoff=TRAINING_CUTOFF, built_at=None):
    cases = []; partitions = []
    for day, path in sorted(paths.items()):
        if protocol_for_day(day) != GUARDED_PROTOCOL or day > aware(cutoff).date().isoformat():
            raise ValueError('invalid_training_partition')
        with TemporaryDirectory() as tmp:
            rows, manifest = replay_partition(path, day=day, cutoff=cutoff, projection=Path(tmp)/'cases.sqlite')
        cases.extend(rows); partitions.append(manifest)
    return seal_library(cases, cutoff=cutoff, built_at=built_at or datetime.now(UTC), partitions=partitions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--built-at', help='Reproduce an existing export timestamp offline only.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.download and args.built_at:
        raise ValueError('cannot_backdate_download')
    paths = {day:args.output/f'{day}.jsonl.gz' for day in TRAINING_DAYS}
    if args.download:
        client = EventClient(os.environ.get('REVIEW_INGEST_SECRET', ''))
        for day,path in paths.items():
            count = download_partition(client, day=day, path=path)
            print(canonical({'day':day, 'downloaded_events':count, 'model_calls':0}))
    library = build(paths, built_at=args.built_at)
    (args.output/'library.json').write_text(canonical(library)+'\n')
    summary = library_summary(library)
    (args.output/'summary.json').write_text(canonical(summary)+'\n')
    print(canonical(summary))


if __name__ == '__main__':
    main()
