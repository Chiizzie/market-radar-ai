"""Signed, fixed-destination archive delivery. Never enables trading or retries."""
import hashlib
import hmac
import json
import requests
from .plan_review import export_review

ENDPOINT = 'https://project--97051425-8afb-4ea6-bf3e-f6e5fc127ba3.lovable.app/api/public/reviews/ingest'
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
