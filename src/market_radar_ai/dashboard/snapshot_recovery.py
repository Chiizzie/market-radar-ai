"""Restore verified original dashboard captures as history, without invoking paper review."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import requests
from urllib3.util import Timeout

from ..agents.research_artifacts import EvidenceBank, GitHubReader, restore_previous_bank
from .snapshot_delivery import ENDPOINT, MAX_BYTES
from .snapshot_receipts import ReceiptUnavailable, lookup, signed_headers, stored_at


def failure(phase, reason, checked, started, ended, status=None):
    details = {'phase': phase, 'reason': reason, 'ids_requested': checked,
               'elapsed_seconds': round(max(0, (ended - started).total_seconds()), 3)}
    if status is not None:
        details['http_status'] = status
    return details


def restore_batch(bank, *, secret, session, clock, limit):
    if type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError('invalid_archive_batch_size')
    result = {'state': 'complete', 'candidates': 0, 'already_stored': 0, 'missing_observed': 0,
              'verified': [], 'pending': [], 'unverified': [], 'unchecked': 0, 'failures': [],
              'model_calls': 0, 'trade_authorized': False}
    pending = {}
    now = clock()
    for row in bank.rows('capture_delivery'):
        if (row.get('client_state') == 'unconfirmed' and row.get('body_state') in ('archived_exact', 'reconstructed_exact')
                and row['expires_at_epoch'] + 60 <= now.timestamp() and row.get('trade_authorized') is False):
            key = row['snapshot_id']
            if key in pending and any(row[k] != pending[key][k] for k in ('generated_at_dublin', 'expires_at_epoch')):
                raise ValueError('conflicting_original_receipt')
            pending[key] = row
    keys = sorted(pending, key=lambda k: (pending[k]['expires_at_epoch'], k), reverse=True)
    result['candidates'] = len(keys)
    missing = []
    # Keep the signed request under typical 2 KiB proxy URI limits even after percent encoding.
    for start in range(0, len(keys), 16):
        group = keys[start:start + 16]
        started = clock()
        try:
            receipts = lookup(group, secret=secret, now=started, session=session, seconds=60)
        except ReceiptUnavailable as exc:
            result['unchecked'] = len(keys) - start
            result['missing_observed'] = len(missing)
            result['pending'] = missing
            result['failures'].append(failure('initial_lookup', exc.reason, len(group), started, clock(), exc.status))
            # A slow batch must not hide the newest capture. Probe its exact identity
            # once, using the same route and request shape as the live receipt check.
            if exc.reason != 'read_timeout' or len(group) == 1:
                result['state'] = 'storage_unavailable'
                return result
            started = clock()
            try:
                receipts = lookup(group[:1], secret=secret, now=started, session=session, seconds=45)
            except ReceiptUnavailable as single:
                result['failures'].append(failure('single_lookup', single.reason, 1, started, clock(), single.status))
                result['state'] = 'storage_unavailable'
                return result
            result['unchecked'] -= 1
        for row in receipts:
            key = row['snapshot_id']
            if row['state'] == 'absent':
                missing.append(key)
            elif stored_at(row, pending[key]) is not None:
                result['already_stored'] += 1
            else:
                result['unverified'].append(key)
        if result['unchecked']:
            break
    result['missing_observed'] = len(missing)
    attempted = []
    for key in missing[:limit]:
        original = pending[key]
        text = bank.get('recovery_snapshot', key)
        body = text.encode('utf-8') if isinstance(text, str) else b''
        if len(body) > MAX_BYTES or hashlib.sha256(body).hexdigest() != key:
            result['unverified'].append(key)
            continue
        capture = json.loads(body)
        if any(original[k] != capture.get(k) for k in ('generated_at_dublin', 'expires_at_epoch')):
            result['unverified'].append(key)
            continue
        attempted.append(key)
        started = clock()
        headers = signed_headers(secret, started, b'scanner-snapshot-archive-v1\n' + body)
        try:
            response = session.put(ENDPOINT, data=body,
                headers={**headers, 'Content-Type': 'application/json; charset=utf-8'},
                timeout=Timeout(total=45, connect=5), allow_redirects=False)
            if response.status_code == 409:
                continue  # Another ingest may have won. Verify the stored identity below.
            if response.status_code in (400, 422):
                result['failures'].append(failure('archive_write', 'http_status', 1, started, clock(), response.status_code))
                result['unverified'].append(key)
                continue
            if response.status_code != 200:
                result['failures'].append(failure('archive_write', 'http_status', 1, started, clock(), response.status_code))
                break
            ack = response.json()
            if not isinstance(ack, dict) or ack.get('ok') is not True or ack.get('state') != 'archived' or ack.get('snapshot_id') != key:
                result['failures'].append(failure('archive_write', 'invalid_acknowledgement', 1, started, clock()))
                break
        except (requests.RequestException, TimeoutError, ValueError) as exc:
            if isinstance(exc, requests.ConnectTimeout):
                reason = 'connect_timeout'
            elif isinstance(exc, (requests.ReadTimeout, TimeoutError)):
                reason = 'read_timeout'
            elif isinstance(exc, ValueError):
                reason = 'invalid_acknowledgement'
            else:
                reason = 'transport_error'
            result['failures'].append(failure('archive_write', reason, 1, started, clock()))
            break  # A lost response may still commit. Verify before any further writes.
    if attempted:
        started = clock()
        try:
            observed = lookup(attempted, secret=secret, now=started, session=session, seconds=60)
        except ReceiptUnavailable as exc:
            result['state'] = 'storage_unavailable'
            result['pending'] = missing
            result['failures'].append(failure('readback', exc.reason, len(attempted), started, clock(), exc.status))
            return result
        for row in observed:
            key = row['snapshot_id']
            received = stored_at(row, pending[key])
            if received is not None:
                result['verified'].append({'snapshot_id': key, 'run_id': pending[key]['run_id'],
                    'original_generated_at': pending[key]['generated_at_dublin'], 'received_at': row['received_at'],
                    'recovered_from_archive': row['recovered_from_archive'] is True})
    verified = {r['snapshot_id'] for r in result['verified']}
    result['pending'] = [k for k in missing if k not in verified]
    if result['unchecked']:
        result['state'] = 'storage_unavailable'
    elif result['unverified'] or any(k not in verified for k in attempted):
        result['state'] = 'incomplete'
    elif result['pending']:
        result['state'] = 'more_pending'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/dashboard-recovery/report.json'))
    args = parser.parse_args()
    clock = lambda: datetime.now(UTC)
    if (os.getenv('GITHUB_REPOSITORY') != 'Chiizzie/market-radar-ai' or os.getenv('GITHUB_REF') != 'refs/heads/main'
            or os.getenv('GITHUB_WORKFLOW_REF') != 'Chiizzie/market-radar-ai/.github/workflows/dashboard-delivery-recovery.yml@refs/heads/main'):
        raise SystemExit('dashboard_archive_workflow_scope_required')
    secret = os.getenv('REVIEW_INGEST_SECRET', '')
    if len(secret) < 32:
        raise SystemExit('dashboard_archive_not_configured')
    reader = GitHubReader(os.getenv('GH_TOKEN'))
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'evidence.sqlite'
        source_run = restore_previous_bank(reader, reader.previous_runs(), path)
        if not source_run:
            raise SystemExit('verified_source_bank_required')
        bank = EvidenceBank(path)
        try:
            local = clock().astimezone(ZoneInfo('Europe/Dublin'))
            limit = 2 if local.weekday() < 5 and 8 <= local.hour < 23 else 12
            with requests.Session() as session:
                report = restore_batch(bank, secret=secret, session=session, clock=clock, limit=limit)
        finally:
            bank.close()
    report.update(source_bank_run=source_run, checked_at_dublin=clock().astimezone(ZoneInfo('Europe/Dublin')).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: len(v) if isinstance(v, list) and k != 'failures' else v for k, v in report.items()}))
    return int(report['state'] not in ('complete', 'more_pending'))


if __name__ == '__main__':
    raise SystemExit(main())
