"""Signed, fixed-destination archive delivery. Never enables trading or retries."""
import hashlib
import hmac
import json
import requests
from .plan_review import export_review

ENDPOINT = 'https://pixel-perfect-replay-32614.lovable.app/api/public/reviews/ingest'
MAX_BYTES = 2 * 1024 * 1024


def deliver(capture, catalogue, draft, audit, *, env, clock, session=None):
    if (env.get('GITHUB_REPOSITORY') != 'Chiizzie/market-radar-ai'
            or env.get('GITHUB_REF') != 'refs/heads/phase-1/market-data-layer'
            or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_RUN_ATTEMPT') != '1'
            or env.get('SEND_LOVABLE_REVIEW') != 'true'):
        raise ValueError('manual_archive_delivery_required')
    secret = env.get('REVIEW_INGEST_SECRET', '')
    if len(secret) < 32:
        raise ValueError('ingestion_secret_missing_or_invalid')
    now = clock()
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    review = export_review(capture, catalogue, draft, audit, now=now)
    body = (json.dumps(review, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(body) > MAX_BYTES:
        raise ValueError('archive_too_large')
    timestamp = str(int(now.timestamp()))
    signature = hmac.new(secret.encode('utf-8'), timestamp.encode('ascii') + b'.' + body,
                         hashlib.sha256).hexdigest()
    try:
        response = (session or requests).post(ENDPOINT, data=body,
            headers={'Content-Type':'application/json; charset=utf-8',
                     'X-Timestamp':timestamp, 'X-Signature':'sha256=' + signature},
            timeout=(10, 30), allow_redirects=False)
        # A duplicate/409 is not proof of equal content or a confirmed new write.
        if response.status_code != 200:
            raise ValueError()
        result = response.json()
        if result.get('ok') is not True or result.get('snapshot_id') != review['snapshot_id']:
            raise ValueError()
    except Exception:
        raise RuntimeError('Dashboard archive delivery unconfirmed; inspect storage before retry.') from None
    return {'state':'dashboard_archive_delivery_confirmed', 'snapshot_id':review['snapshot_id'],
            'trade_authorized':False}


# Verified completed review from run 41706847328; no new AI calls.
PINNED_FILES = {'capture.json': '1d5b666c962c3aa2b9066941e36633a801eacd65b42620dbfd490e4198edbb45', 'catalogue.json': 'fc8c796099792b6b8f33dea04e50dbae24d966cc73ea084e3d4b0fb0a796bbbb', 'draft.json': '4d6a7306f4c76d0e6258cca3eb037dc048bd0ee3e138f54750a1a442b1d159b1', 'review.json': '2227b30ddcfadfe8cc56c3a498d7c7ec396305ebec2c8e612ca6b96101f3eac6'}

def load_pinned_bundle(directory):
    from pathlib import Path
    result = []
    for name, expected in PINNED_FILES.items():
        raw = (Path(directory) / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('historical_evidence_digest_mismatch')
        result.append(json.loads(raw))
    return result


def main():
    import os
    import sys
    from datetime import datetime, timezone
    result = deliver(*load_pinned_bundle(sys.argv[1]), env=os.environ,
                     clock=lambda: datetime.now(timezone.utc))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
