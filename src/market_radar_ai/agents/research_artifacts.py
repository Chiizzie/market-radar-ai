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
    if packets is not None and not isinstance(packets.get('packets'), list):
        raise ValueError('packet_capture_schema')
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
    links = []
    for p in (packets or {}).get('packets', []):
        if digest(p['packet']) != p['packet_id']:
            raise ValueError('candidate_packet_hash')
        links.append({'packet_id': p['packet_id'], 'candidate_id': p['packet']['candidate_id'],
                      'assembled_at': p['packet']['assembled_at']})
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
        snapshots = list(self.rows('capture'))
        runs = list(self.rows('run'))
        covered = {(s['run_id'], s['attempt']) for s in snapshots}
        missing = [r['id'] for r in runs if (r['id'], r['attempt']) not in covered]
        return {'schema_version': 'evidence-intake-summary-v1', 'completed_scanner_attempts': len(runs),
            'conclusions': dict(Counter(r['conclusion'] for r in runs)),
            'capture_snapshots': len(snapshots), 'missing_capture_run_ids': missing,
            'incomplete_capture_artifacts': [s['artifact_id'] for s in snapshots if s['missing_files']],
            'discovery_candidate_observations': sum(s['discovery_observations'] for s in snapshots),
            'qualification_observations': sum(s['qualified_observations'] for s in snapshots),
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
        if not re.fullmatch(r'/(runs(?:/\d+/artifacts)?|artifacts/\d+/zip|workflows/performance-intelligence.yml/runs)', path):
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


def collect(reader, runs, bank, output, *, maximum_new_artifacts=120):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ordered = sorted(runs, key=lambda r: (r['created_at'], r['id']), reverse=True)
    artifacts_by_run = {}
    pending, downloaded = [], 0

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

    sources = {}
    for name, prefix, target in [('Execution research and readiness', 'execution-research-', 'execution'),
                                  ('Manual shared paper portfolio', 'manual-portfolio-', 'manual')]:
        for run in ordered:
            if run['name'] != name or run['conclusion'] != 'success':
                continue
            candidates = [a for a in artifacts(run) if a['name'].startswith(prefix) and not a['expired']]
            if not candidates:
                continue  # An out-of-window green run may have no report.
            artifact = max(candidates, key=lambda a: a['created_at'])
            files = zip_members(reader.download(artifact), {'report.json', 'source-events.jsonl.gz', 'ledger.json.gz'})
            required = {'report.json', 'source-events.jsonl.gz'} | ({'ledger.json.gz'} if target == 'manual' else set())
            if not required <= set(files):
                raise ValueError('incomplete_' + target + '_artifact')
            dest = output / target; dest.mkdir(exist_ok=True)
            for filename, raw in files.items():
                (dest / filename).write_bytes(raw)
            sources[target] = {'run_id': run['id'], 'artifact_id': artifact['id'], 'digest': artifact.get('digest')}
            break
    if 'execution' not in sources:
        raise ValueError('no_completed_execution_evidence')
    for run in ordered:
        if run['name'] != 'Scheduled research collection' or run['status'] != 'completed':
            continue
        attempt = run.get('run_attempt', 1)
        bank.put('run', f"{run['id']}:{attempt}", {k: run[k] for k in ('id', 'head_sha', 'created_at', 'conclusion')} | {'attempt': attempt})
        for artifact in artifacts(run):
            kind = 'capture' if artifact['name'] == 'scheduled-capture-' + str(run['id']) else \
                   'context' if artifact['name'] == 'market-context-' + str(run['id']) else None
            if not kind or artifact['expired'] or bank.has(kind, artifact['id']):
                continue
            if artifact.get('expires_at') and aware(artifact['expires_at']) <= datetime.now(UTC):
                continue
            if downloaded >= maximum_new_artifacts:
                pending.append(artifact['id']); continue
            names = CAPTURE_FILES | {'opening-session.json'} if kind == 'capture' else {'report.json'}
            files = zip_members(reader.download(artifact), names)
            downloaded += 1
            if kind == 'capture':
                bank.put(kind, artifact['id'], capture_snapshot(files, run=run, artifact=artifact))
            elif 'report.json' in files:
                report = json.loads(files['report.json'])
                bank.put(kind, artifact['id'], {'report': report, 'sha256': digest(report),
                    # GitHub's creation time proves availability conservatively.
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
    (output / 'contexts.json').write_text(canonical(list(bank.rows('context'))) + '\n')
    (output / 'experiments.json').write_text(json.dumps(summarize_latest(bank.rows('frozen')), indent=2) + '\n')
    (output / 'intake.json').write_text(json.dumps({'sources': sources, 'new_artifacts_indexed': downloaded,
        'frozen_artifacts_read': frozen_downloads,
        'pending_artifact_ids': pending, 'state': 'backfill_pending' if pending else 'available_artifacts_indexed',
        **bank.summary()}, indent=2) + '\n')
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
        sources = collect(reader, runs, bank, args.output)
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
