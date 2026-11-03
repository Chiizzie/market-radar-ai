"""Scoped capture-only scanner delivery; no models, orders or automatic retries."""
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path

import requests
from .export import build_snapshot

ENDPOINT = 'https://pixel-perfect-replay-32614.lovable.app/api/public/snapshots/ingest'
MAX_BYTES = 2 * 1024 * 1024


def deliver(capture, *, env, clock, evidence=None, session=None):
    from .collection_schedule import scheduled_scope
    now = clock()
    manual = (env.get('GITHUB_REPOSITORY') == 'Chiizzie/market-radar-ai'
              and env.get('GITHUB_REF') == 'refs/heads/phase-1/market-data-layer'
              and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
              and env.get('GITHUB_RUN_ATTEMPT') == '1')
    if (not (manual or scheduled_scope(env, now))
            or env.get('SEND_SCANNER_SNAPSHOT') != 'true'):
        raise ValueError('manual_snapshot_delivery_required')
    secret = env.get('REVIEW_INGEST_SECRET', '')
    if len(secret) < 32:
        raise ValueError('ingestion_secret_missing_or_invalid')
    snapshot = build_snapshot(capture, now=now, evidence=evidence)
    if not any(snapshot['markets'].values()):
        raise ValueError('empty_capture_not_deliverable')
    body = (json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
    if len(body) > MAX_BYTES:
        raise ValueError('snapshot_too_large')
    snapshot_id = hashlib.sha256(body).hexdigest()
    timestamp = str(int(now.timestamp()))
    signature = hmac.new(secret.encode(), timestamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
    try:
        response = (session or requests).post(ENDPOINT, data=body,
            headers={'Content-Type': 'application/json; charset=utf-8',
                     'X-Timestamp': timestamp, 'X-Signature': 'sha256='+signature},
            timeout=(10, 30), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError()
        result = response.json()
        if result.get('ok') is not True or result.get('snapshot_id') != snapshot_id:
            raise ValueError()
    except Exception:
        raise RuntimeError('Scanner delivery unconfirmed; inspect storage before retry.') from None
    return {'state': 'scanner_snapshot_delivery_confirmed', 'snapshot_id': snapshot_id,
            'coverage': snapshot['coverage'], 'generated_at_dublin': snapshot['generated_at_dublin'],
            'expires_at_epoch': snapshot['expires_at_epoch'],
            'trade_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    result = deliver(json.loads(args.capture.read_text()), env=os.environ,
        clock=lambda: datetime.now(timezone.utc),
        evidence=json.loads(args.evidence.read_text()) if args.evidence else None)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
