"""Read-only GitHub artifact intake and additive, compressed evidence index.

Only public scanner research artifacts are accepted. No provider/model/broker
credentials, database reads, notification calls or history deletion.
"""
import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
import gzip
import hashlib
from io import BytesIO
import json
import os
import re
from pathlib import Path, PurePosixPath
import sqlite3
import time
from zipfile import ZipFile
import zlib
from zoneinfo import ZoneInfo

import requests

from .candidate_packages import canonical, digest
from .paper_comparison import aware

REPO = 'Chiizzie/market-radar-ai'
API = 'https://api.github.com/repos/' + REPO
CAPTURE_FILES = {'discovery-selection.json', 'qualification.json', 'paper-review-packets.json', 'run-diagnostics.json'}
MAX_ZIP = 350_000_000
MAX_MEMBER = 250_000_000
EXPORT_STEPS = {
    'execution': 'Reconstruct cost scenarios and shared portfolios from durable evidence',
    'manual': 'Replay separate accounts and verify complete ledger recovery',
}


def zip_members(raw, names):
    """Read named basenames without extracting paths or executing archive files."""
    if len(raw) > MAX_ZIP:
        raise ValueError('research_zip_capacity')
    result = {}
    with ZipFile(BytesIO(raw)) as archive:
        if len(archive.infolist()) > 300:
            raise ValueError('research_zip_member_capacity')
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe_artifact_path')
            if path.name not in names or entry.is_dir():
                continue
            if path.name in result or entry.file_size > MAX_MEMBER:
                raise ValueError('ambiguous_or_oversized_artifact_member')
            result[path.name] = archive.read(entry)
    return result


def verified_packets(document):
    if document.get('trade_authorized') is not False:
        raise ValueError('research_capture_scope')
    if not isinstance(document.get('packets'), list):
        raise ValueError('packet_capture_schema')
    for item in document['packets']:
        if digest(item['packet']) != item['packet_id']:
            raise ValueError('candidate_packet_hash')
    return document['packets']


def capture_snapshot(files, *, run, artifact):
    """Lossless funnel states, grouped to avoid repeating thousands of deferrals.

    Full market prices remain in source captures and enrolled source journals.
    A discovery deferral is not a strategy rejection or a zero-return trade.
    """
    documents = {name: json.loads(value) for name, value in files.items() if name in CAPTURE_FILES}
    selection = documents.get('discovery-selection.json')
    qualification = documents.get('qualification.json')
    packets = documents.get('paper-review-packets.json')
    for d in (selection, qualification, packets):
        if d is not None and d.get('trade_authorized') is not False:
            raise ValueError('research_capture_scope')
    if selection is not None and (selection.get('schema_version') != 'stock-selection-trace-v1' or not isinstance(selection.get('symbols'), list)):
        raise ValueError('discovery_capture_schema')
    if qualification is not None and (qualification.get('schema_version') != 'free-qualification-v1' or not isinstance(qualification.get('candidates'), list)):
        raise ValueError('qualification_capture_schema')
    groups = defaultdict(list)
    seen = set()
    dimensions = ('snapshot_status', 'selection_reason', 'screen_lane', 'technical_status',
                  'technical_reasons', 'detail_selected', 'detail_lane')
    for row in (selection or {}).get('symbols', []):
        if row['symbol'] in seen:
            raise ValueError('duplicate_discovery_symbol')
        seen.add(row['symbol'])
        key = canonical({k: row.get(k) for k in dimensions})
        groups[key].append(row['symbol'])
    fields = ('candidate_id', 'symbol', 'market', 'eligible_for_paid_review', 'eligible_for_paper_review',
              'blockers', 'paper_blockers', 'technical_checks', 'paper_risk_check', 'conditional_paper_plan')
    qualified = [{k: row.get(k) for k in fields} for row in (qualification or {}).get('candidates', [])]
    if len({r['candidate_id'] for r in qualified}) != len(qualified):
        raise ValueError('duplicate_qualified_candidate')
    packet_rows = verified_packets(packets) if packets is not None else []
    links = [{'packet_id': p['packet_id'], 'candidate_id': p['packet']['candidate_id'],
              'assembled_at': p['packet']['assembled_at']} for p in packet_rows]
    diagnostics = documents.get('run-diagnostics.json', {})
    opening = {}
    if 'opening-session.json' in files:
        brief = json.loads(files['opening-session.json'])
        if brief.get('schema_version') != 'opening-session-brief-v1' or brief.get('trade_authorized') is not False:
            raise ValueError('opening_capture_scope')
        opening['opening_session'] = brief
    return {'schema_version': 'candidate-funnel-snapshot-v1', **opening,
        'run_id': run['id'], 'attempt': run.get('run_attempt', 1), 'head_sha': run['head_sha'],
        'run_conclusion': run['conclusion'], 'artifact_id': artifact['id'],
        'artifact_created_at': artifact['created_at'], 'artifact_digest': artifact.get('digest'),
        'source_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())},
        'observed_at': (selection or {}).get('observed_at'),
        'qualified_at': (qualification or {}).get('evaluated_at'),
        'discovery_groups': [{'state': json.loads(k), 'symbols': sorted(v)} for k, v in sorted(groups.items())],
        'qualified_candidates': qualified, 'packet_links': links,
        'discovery_coverage': diagnostics.get('discovery', {}).get('coverage'),
        'discovery_observations': len(seen), 'qualified_observations': len(qualified),
        'missing_files': sorted(CAPTURE_FILES - set(documents)),
        'trade_authorized': False, 'model_calls': 0}


def research_snapshot(body):
    if body is None:
        return None
    try:
        snapshot = json.loads(body.decode('utf-8'))
    except (UnicodeError, ValueError):
        return None
    if (not isinstance(snapshot, dict) or snapshot.get('schema_version') != '1.0'
            or snapshot.get('mode') != 'RESEARCH_ONLY' or snapshot.get('live_orders_enabled') is not False):
        return None
    return snapshot


def recover_request(raw, receipt, archived):
    """Return exact request bytes only when the collector's fingerprint agrees."""
    from ..dashboard.export import build_snapshot
    from ..dashboard.snapshot_delivery import MAX_BYTES, snapshot_bytes
    expected = receipt['snapshot_id']
    if archived is not None and hashlib.sha256(archived).hexdigest() == expected:
        body, source = archived, 'archived_exact'
    else:
        inputs = zip_members(raw, {'enriched-capture.json', 'news.json'})
        try:
            snapshot = build_snapshot(json.loads(inputs['enriched-capture.json']),
                now=aware(receipt['generated_at_dublin']), evidence=json.loads(inputs['news.json']))
            body = snapshot_bytes(snapshot)
        except (ValueError, KeyError, TypeError, ArithmeticError, AttributeError, IndexError):
            # A malformed legacy input cannot establish the original request.
            return None, 'unverified'
        if hashlib.sha256(body).hexdigest() != expected:
            return None, 'unverified'
        source = 'reconstructed_exact'
    snapshot = research_snapshot(body)
    if (len(body) > MAX_BYTES or snapshot is None
            or any(snapshot.get(k) != receipt[k] for k in ('generated_at_dublin', 'expires_at_epoch', 'coverage'))):
        return None, 'unverified'
    return body.decode('utf-8'), source


def retain_delivery(bank, raw, files, *, run, artifact):
    parts = zip_members(raw, {'delivery.json', 'dashboard.json'})
    archived = parts.get('dashboard.json')
    meta = {'run_id': run['id'], 'attempt': run.get('run_attempt', 1), 'artifact_id': artifact['id'],
            'artifact_digest': artifact.get('digest'), 'client_state': 'receipt_missing',
            'body_state': 'unavailable', 'packet_ids': None, 'trade_authorized': False}
    states = {'scanner_snapshot_delivery_confirmed': 'confirmed',
              'scanner_snapshot_delivery_unconfirmed': 'unconfirmed'}
    receipt = None
    if 'delivery.json' in parts:
        meta['client_state'] = 'invalid_receipt'
        try:
            receipt = json.loads(parts['delivery.json'])
        except (UnicodeError, ValueError):
            pass
    if (isinstance(receipt, dict) and isinstance(receipt.get('state'), str) and receipt['state'] in states
            and receipt.get('trade_authorized') is False and isinstance(receipt.get('coverage'), dict)
            and isinstance(receipt.get('generated_at_dublin'), str) and type(receipt.get('expires_at_epoch')) is int
            and isinstance(receipt.get('snapshot_id'), str) and re.fullmatch('[0-9a-f]{64}', receipt['snapshot_id'])):
        meta.update(client_state=states[receipt['state']], snapshot_id=receipt['snapshot_id'],
                    generated_at_dublin=receipt['generated_at_dublin'], expires_at_epoch=receipt['expires_at_epoch'])
        if meta['client_state'] == 'confirmed':
            meta['body_state'] = 'not_requested'
        else:
            body, meta['body_state'] = recover_request(raw, receipt, archived)
            if body is not None:
                bank.put('recovery_snapshot', receipt['snapshot_id'], body)
    if meta['body_state'] in {'unavailable', 'unverified'} and research_snapshot(archived) is not None:
        # This is the original display export, with its own clock and hash.
        # It is not evidence of which bytes the server received.
        export_id = hashlib.sha256(archived).hexdigest()
        bank.put('recovery_export', export_id, archived.decode('utf-8'))
        meta['local_export_sha256'] = export_id
    if meta['client_state'] != 'confirmed' and 'paper-review-packets.json' in files:
        packets = verified_packets(json.loads(files['paper-review-packets.json']))
        for packet in packets:
            bank.put('recovery_packet', packet['packet_id'], packet['packet'])
        meta['packet_ids'] = [p['packet_id'] for p in packets]
    # Write last, so a retry completes any interrupted body or packet archive.
    bank.put('capture_delivery', artifact['id'], meta)


class EvidenceBank:
    """An additive artifact index; source records are never updated or deleted."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA cache_size=-4096')
        self.db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,sha TEXT,payload BLOB,'
                        'PRIMARY KEY(kind,id))')

    def put(self, kind, key, payload):
        sha = digest(payload)
        old = self.db.execute('SELECT sha,payload FROM records WHERE kind=? AND id=?', (kind, str(key))).fetchone()
        if old:
            if old[0] != sha or digest(json.loads(zlib.decompress(old[1]))) != sha:
                raise ValueError('immutable_evidence_conflict')
            return False
        if self.path.stat().st_size > 1_000_000_000:
            raise ValueError('evidence_bank_capacity_preserve_history')
        self.db.execute('INSERT INTO records VALUES(?,?,?,?)',
                        (kind, str(key), sha, zlib.compress(canonical(payload).encode())))
        self.db.commit()
        return True

    def has(self, kind, key):
        return self.db.execute('SELECT 1 FROM records WHERE kind=? AND id=?', (kind, str(key))).fetchone() is not None

    def get(self, kind, key):
        row = self.db.execute('SELECT sha,payload FROM records WHERE kind=? AND id=?', (kind, str(key))).fetchone()
        if row is None:
            return None
        value = json.loads(zlib.decompress(row[1]))
        if digest(value) != row[0]:
            raise ValueError('evidence_bank_corruption')
        return value

    def rows(self, kind):
        for sha, data in self.db.execute('SELECT sha,payload FROM records WHERE kind=? ORDER BY id', (kind,)):
            row = json.loads(zlib.decompress(data))
            if digest(row) != sha:
                raise ValueError('evidence_bank_corruption')
            yield row

    def summary(self):
        summary_fields = ('run_id', 'attempt', 'artifact_id', 'missing_files', 'artifact_created_at',
                          'discovery_observations', 'qualified_observations')
        snapshots = [{field: row[field] for field in summary_fields} for row in self.rows('capture')]
        runs = list(self.rows('run'))
        deliveries = list(self.rows('capture_delivery'))
        covered = {(s['run_id'], s['attempt']) for s in snapshots}
        missing = [r['id'] for r in runs if (r['id'], r['attempt']) not in covered]
        return {'schema_version': 'evidence-intake-summary-v1', 'completed_scanner_attempts': len(runs),
            'conclusions': dict(Counter(r['conclusion'] for r in runs)),
            'capture_snapshots': len(snapshots), 'missing_capture_run_ids': missing,
            'incomplete_capture_artifacts': [s['artifact_id'] for s in snapshots if s['missing_files']],
            'discovery_candidate_observations': sum(s['discovery_observations'] for s in snapshots),
            'qualification_observations': sum(s['qualified_observations'] for s in snapshots),
            'delivery_recovery': {
                'client_states': dict(Counter(d['client_state'] for d in deliveries)),
                'outbound_bodies': dict(Counter(d['body_state'] for d in deliveries)),
                'local_exports_preserved': sum('local_export_sha256' in d for d in deliveries),
                'packet_occurrences_preserved': sum(len(d['packet_ids'] or []) for d in deliveries),
                'unique_packets_preserved': self.db.execute(
                    "SELECT count(*) FROM records WHERE kind='recovery_packet'").fetchone()[0]},
            'first_capture_at': min((s['artifact_created_at'] for s in snapshots), default=None),
            'last_capture_at': max((s['artifact_created_at'] for s in snapshots), default=None),
            'full_historical_coverage_established': False,
            'note': 'Repeated candidate observations are not independent trades. Missing/failed runs remain visible. '
                    'Retained artifact coverage does not prove that every scheduled invocation occurred.'}

    def close(self):
        self.db.commit()
        self.db.close()


class GitHubReader:
    def __init__(self, token, *, session=None):
        if not token:
            raise ValueError('github_read_token_required')
        self.session = session or requests.Session()
        self.headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28'}

    def get(self, path, *, params=None, binary=False):
        if not re.fullmatch(r'/(runs(?:/\d+/(?:artifacts|attempts/\d+/jobs))?|artifacts/\d+/zip|workflows/performance-intelligence\.yml/runs)', path):
            raise ValueError('research_actions_read_only')
        for attempt in range(3):
            try:
                response = self.session.get(API + '/actions' + path, params=params, headers=self.headers,
                    timeout=(10, 60), allow_redirects=True, stream=binary)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    response.close(); time.sleep(attempt + 1); continue
                if response.status_code != 200:
                    response.close()
                    raise RuntimeError('github_artifact_read_failed_http_' + str(response.status_code))
                if not binary:
                    result = response.json(); response.close(); return result
                data = bytearray()
                for chunk in response.iter_content(1024 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_ZIP:
                        response.close(); raise ValueError('research_zip_capacity')
                response.close()
                return bytes(data)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise RuntimeError('github_artifact_transport_unavailable') from None
                time.sleep(attempt + 1)

    def runs(self, day):
        result = []
        for page in range(1, 21):
            batch = self.get('/runs', params={'created': day, 'per_page': 100, 'page': page})['workflow_runs']
            result.extend(r for r in batch if r['head_branch'] == 'main' and
                          (r.get('head_repository') or {}).get('full_name') == REPO)
            if len(batch) < 100:
                return result
        raise ValueError('workflow_inventory_capacity')

    def artifacts(self, run):
        return self.get('/runs/' + str(run['id']) + '/artifacts', params={'per_page': 100})['artifacts']

    def export_receipt(self, run, target):
        attempt = run.get('run_attempt', 1)
        jobs = self.get(f"/runs/{run['id']}/attempts/{attempt}/jobs", params={'per_page': 100})['jobs']
        for job in jobs:
            if job.get('run_id') != run['id'] or job.get('run_attempt') != attempt:
                continue
            for step in job.get('steps', []):
                if step['name'] == EXPORT_STEPS[target] and step['conclusion'] == 'success':
                    return {'job_id': job['id'], 'export_completed_at': step['completed_at'],
                            'job_completed_at': job['completed_at']}
        return {}

    def previous_runs(self):
        runs = self.get('/workflows/performance-intelligence.yml/runs',
                        params={'status': 'completed', 'per_page': 100})['workflow_runs']
        return [r for r in runs if r['head_branch'] == 'main' and (r.get('head_repository') or {}).get('full_name') == REPO]

    def download(self, artifact):
        if artifact.get('expired') or (artifact.get('expires_at') and aware(artifact['expires_at']) <= datetime.now(UTC)):
            raise ValueError('source_artifact_expired')
        raw = self.get('/artifacts/' + str(artifact['id']) + '/zip', binary=True)
        if artifact.get('digest') and artifact['digest'] != 'sha256:' + hashlib.sha256(raw).hexdigest():
            raise ValueError('github_artifact_digest_mismatch')
        return raw


def collect(reader, runs, bank, output, *, maximum_new_artifacts=120, catch_up_deadline=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ordered = sorted(runs, key=lambda r: (r['created_at'], r['id']), reverse=True)
    artifacts_by_run = {}
    pending, downloaded = [], 0
    queue = []
    started = datetime.now(UTC)

    def artifacts(run):
        if run['id'] not in artifacts_by_run:
            key = f"{run['id']}:{run.get('run_attempt', 1)}"
            saved = bank.get('inventory', key)
            if saved is None:
                saved = {'run': run, 'artifacts': reader.artifacts(run)}
                if run['status'] == 'completed':
                    bank.put('inventory', key, saved)
            artifacts_by_run[run['id']] = saved['artifacts']
        return artifacts_by_run[run['id']]

    for run in ordered:
        if run['name'] != 'Scheduled research collection' or run['status'] != 'completed':
            continue
        attempt = run.get('run_attempt', 1)
        bank.put('run', f"{run['id']}:{attempt}", {k: run[k] for k in ('id', 'head_sha', 'created_at', 'conclusion')} | {'attempt': attempt})
        for artifact in artifacts(run):
            kind = 'capture' if artifact['name'] == 'scheduled-capture-' + str(run['id']) else \
                   'context' if artifact['name'] == 'market-context-' + str(run['id']) else None
            if not kind or artifact['expired']:
                continue
            expiry = aware(artifact['expires_at']) if artifact.get('expires_at') else None
            if expiry is not None and expiry <= started:
                continue
            indexed = bank.has(kind, artifact['id'])
            # Backfill previously indexed failed attempts without altering the
            # original funnel record. New captures share the same ZIP download.
            needs_delivery = (kind == 'capture' and (not indexed or run['conclusion'] != 'success')
                              and not bank.has('capture_delivery', artifact['id']))
            if indexed and not needs_delivery:
                continue
            queue.append((expiry, run, artifact, kind, indexed))
    # Expiring archives take precedence. Stable sorting keeps newest-first
    # intake for other sources, including older inventories without an expiry.
    urgent_by = started + timedelta(hours=36)
    queue.sort(key=lambda item: min(item[0], urgent_by) if item[0] else urgent_by)
    urgent_pending = []
    for expiry, run, artifact, kind, indexed in queue:
        if downloaded >= maximum_new_artifacts and (
                catch_up_deadline is None or time.monotonic() >= catch_up_deadline
                or downloaded >= 8 * maximum_new_artifacts):
            pending.append(artifact['id'])
            if expiry is not None and expiry <= urgent_by:
                urgent_pending.append(expiry)
            continue
        names = CAPTURE_FILES | {'opening-session.json'} if kind == 'capture' else {'report.json'}
        raw = reader.download(artifact)
        files = zip_members(raw, names)
        downloaded += 1
        if kind == 'capture':
            if not indexed:
                bank.put(kind, artifact['id'], capture_snapshot(files, run=run, artifact=artifact))
            if not bank.has('capture_delivery', artifact['id']):
                retain_delivery(bank, raw, files, run=run, artifact=artifact)
        elif 'report.json' in files:
            report = json.loads(files['report.json'])
            bank.put(kind, artifact['id'], {'report': report, 'sha256': digest(report),
                'available_at': max(aware(artifact['created_at']), aware(report['as_of'])).isoformat(),
                'artifact_id': artifact['id'], 'artifact_digest': artifact.get('digest')})
    # Frozen experiments already export their complete journals. Recover one
    # latest usable report per day/experiment; keep older snapshots in the bank.
    from .frozen_evaluation import evaluate, summarize_latest
    selected = set(); frozen_downloads = 0
    for run in ordered:
        if run['name'] != 'Scheduled research collection' or run['status'] != 'completed':
            continue
        for artifact in artifacts(run):
            kind = 'strategy' if artifact['name'] == 'strategy-experiment-' + str(run['id']) else \
                   'entry' if artifact['name'] == 'entry-confirmation-' + str(run['id']) else None
            key = (run['created_at'][:10], kind)
            if not kind or key in selected or artifact['expired']:
                continue
            if artifact.get('expires_at') and aware(artifact['expires_at']) <= datetime.now(UTC):
                continue
            if bank.has('frozen_missing', artifact['id']):
                continue
            if bank.has('frozen', artifact['id']):
                selected.add(key); continue
            if frozen_downloads >= 20:
                pending.append(artifact['id']); continue
            files = zip_members(reader.download(artifact), {'report.json', 'events.jsonl'})
            frozen_downloads += 1
            if not {'report.json', 'events.jsonl'} <= set(files):
                bank.put('frozen_missing', artifact['id'], {'artifact_id': artifact['id'],
                    'created_at': artifact['created_at'], 'missing_files': sorted({'report.json', 'events.jsonl'} - set(files))})
                continue
            bank.put('frozen', artifact['id'], evaluate(files, kind))
            selected.add(key)
    sources = {}
    for name, prefix, target in [('Execution research and readiness', 'execution-research-', 'execution'),
                                  ('Manual shared paper portfolio', 'manual-portfolio-', 'manual')]:
        for run in ordered:
            if (run['name'] != name or run['status'] != 'completed'
                    or run['conclusion'] not in ('success', 'failure')):
                continue
            candidates = [a for a in artifacts(run) if a['name'] == prefix + str(run['id']) and not a['expired']]
            if not candidates:
                continue  # An out-of-window green run may have no report.
            receipt = {}
            if run['conclusion'] == 'failure':
                key = f"{run['id']}:{run.get('run_attempt', 1)}:{target}"
                receipt = bank.get('export_step_receipt', key)
                if receipt is None:
                    receipt = reader.export_receipt(run, target)
                    bank.put('export_step_receipt', key, receipt)
                if not receipt:
                    continue
                # Artifacts belong to a run ID across reruns. Only use one uploaded
                # after this attempt's successful producer and before its job ended.
                candidates = [a for a in candidates if a.get('digest') and
                    aware(receipt['export_completed_at']) <= aware(a['created_at']) <= aware(receipt['job_completed_at'])]
                if not candidates:
                    continue
            artifact = max(candidates, key=lambda a: a['created_at'])
            files = zip_members(reader.download(artifact), {'report.json', 'source-events.jsonl.gz', 'ledger.json.gz'})
            required = {'report.json', 'source-events.jsonl.gz'} | ({'ledger.json.gz'} if target == 'manual' else set())
            if not required <= set(files):
                raise ValueError('incomplete_' + target + '_artifact')
            dest = output / target; dest.mkdir(exist_ok=True)
            for filename, raw in files.items():
                (dest / filename).write_bytes(raw)
            sources[target] = {'run_id': run['id'], 'artifact_id': artifact['id'], 'digest': artifact.get('digest'),
                               'workflow_conclusion': run['conclusion'], **receipt}
            break
    (output / 'contexts.json').write_text(canonical(list(bank.rows('context'))) + '\n')
    (output / 'experiments.json').write_text(json.dumps(summarize_latest(bank.rows('frozen')), indent=2) + '\n')
    (output / 'intake.json').write_text(json.dumps({'sources': sources,
        'performance_source_status': 'available' if 'execution' in sources else 'execution_source_missing',
        'new_artifacts_indexed': downloaded,
        'pending_within_36_hours': len(urgent_pending),
        'next_pending_expiry': min(urgent_pending).isoformat() if urgent_pending else None,
        'frozen_artifacts_read': frozen_downloads,
        'pending_artifact_ids': pending, 'state': 'backfill_pending' if pending else 'available_artifacts_indexed',
        **bank.summary()}, indent=2) + '\n')
    if 'execution' not in sources:
        raise ValueError('no_completed_execution_evidence')
    return sources


def restore_previous_bank(reader, runs, destination):
    previous = sorted((r for r in runs if r['name'] == 'Paper performance intelligence' and
                       r['status'] == 'completed'), key=lambda r: r['created_at'], reverse=True)
    expired = False
    for run in previous:
        available = [a for a in reader.artifacts(run) if a['name'].startswith('performance-evidence-bank-')]
        expired = expired or any(a['expired'] for a in available)
        candidates = sorted((a for a in available if not a['expired']), key=lambda a: a['created_at'], reverse=True)
        if candidates:
            files = zip_members(reader.download(candidates[0]), {'evidence-bank.sqlite.gz'})
            if 'evidence-bank.sqlite.gz' not in files:
                raise ValueError('previous_evidence_bank_missing')
            with gzip.GzipFile(fileobj=BytesIO(files['evidence-bank.sqlite.gz'])) as source, Path(destination).open('xb') as out:
                size = 0
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > 1_050_000_000:
                        raise ValueError('evidence_bank_restore_capacity')
                    out.write(chunk)
            return run['id']
    if expired:
        raise ValueError('previous_history_expired_do_not_silently_reset')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/evidence-intake'))
    parser.add_argument('--day', default=datetime.now(UTC).astimezone(ZoneInfo('Europe/Dublin')).date().isoformat())
    parser.add_argument('--after-close-backfill', action='store_true',
                        help='Use spare after-close time for bounded reads of existing GitHub evidence.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reader = GitHubReader(os.environ.get('GH_TOKEN'))
    day = datetime.fromisoformat(args.day).date()
    bank_path = args.output / 'evidence-bank.sqlite'
    restored = restore_previous_bank(reader, reader.previous_runs(), bank_path)
    bank = EvidenceBank(bank_path)
    try:
        first = datetime(2026, 11, 12).date()
        queried = {r['day'] for r in bank.rows('day_inventory')}
        dates = {day, day - timedelta(days=1)}
        dates.update(first + timedelta(days=n) for n in range(max(0, (day - first).days))
                     if (first + timedelta(days=n)).isoformat() not in queried)
        # Inventory complete past dates once; always refresh the current and
        # previous date. Downloads have a separate bounded incremental budget.
        runs, completed_dates = [], []
        for date in sorted(dates, reverse=True)[:32]:
            found = reader.runs(date.isoformat()); runs.extend(found)
            if date < day - timedelta(days=1) and all(r['status'] == 'completed' for r in found):
                completed_dates.append(date.isoformat())
        current_ids = {r['id'] for r in runs}
        runs += [r['run'] for r in bank.rows('inventory') if r['run']['id'] not in current_ids]
        after_close = datetime.now(ZoneInfo('America/New_York')).hour >= 16
        catch_up = time.monotonic() + 12 * 60 if args.after_close_backfill and after_close else None
        sources = collect(reader, runs, bank, args.output, catch_up_deadline=catch_up)
        # Mark a date complete only after its run inventories were retained.
        # A mid-intake failure must not strand unvisited historical runs.
        for date in completed_dates:
            bank.put('day_inventory', date, {'day': date})
    finally:
        bank.close()
        # Preserve partial additive intake even if a later network read failed.
        with bank_path.open('rb') as source, gzip.open(args.output / 'evidence-bank.sqlite.gz', 'wb') as out:
            while chunk := source.read(1024 * 1024):
                out.write(chunk)
    print(canonical({'state': 'research_artifacts_indexed', 'sources': sources,
                     'prior_bank_run': restored, 'model_calls': 0, 'trade_authorized': False}))


if __name__ == '__main__':
    main()
