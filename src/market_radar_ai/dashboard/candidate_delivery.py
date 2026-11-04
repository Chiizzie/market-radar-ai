"""Signed generic research archive; separate from trade-plan/snapshot contracts."""
from datetime import datetime
import hashlib
import hmac
import json
import requests
from ..agents.candidate_packages import canonical
from ..agents.candidate_review import run, STAGES

ENDPOINT = 'https://pixel-perfect-replay-32614.lovable.app/api/public/candidate-reviews/ingest'
MAX_BYTES = 2 * 1024 * 1024


def export_archive(record, capture, feed, audit):
    result = audit['result']
    if (audit.get('schema_version') != 'paid-candidate-review-v1'
            or audit.get('state') != 'completed' or audit.get('trade_authorized') is not False
            or len(audit.get('calls', [])) != 8):
        raise ValueError('incomplete_paid_candidate_review')
    started = datetime.fromisoformat(result['started_at'])
    completed = datetime.fromisoformat(result['completed_at'])
    reviews = iter(result['reviews'])
    # Re-run deterministic source/role/gap checks without calling any model.
    # Only the recorded end time matters for the final freshness label.
    times = iter([started] * 16 + [completed])
    rebuilt = run(record, capture, feed, lambda *_: next(reviews), clock=lambda: next(times))
    if rebuilt != result:
        raise ValueError('candidate_result_does_not_reproduce')
    spent = 0
    for stage, call, review in zip(STAGES, audit['calls'], result['reviews'], strict=True):
        amount = call.get('estimated_cost_microeur')
        if (call.get('stage') != stage or call.get('state') != 'received'
                or call.get('untrusted_response') != review
                or type(amount) is not int or amount < 0):
            raise ValueError('invalid_candidate_usage_record')
        spent += amount
    return {'schema_version': 'candidate-review-archive-v1',
            'package_id': record['package_id'], 'candidate_id': result['candidate_id'],
            # Hash exact package_json UTF-8 bytes; do not reserialize in another language.
            'package_json': canonical(record['package']), 'result_json': canonical(result),
            'completed_at': result['completed_at'], 'evidence_expires_at': result['evidence_expires_at'],
            'review_origin': 'PAID_AI', 'estimated_cost_microeur': spent,
            'reporting_currency': 'EUR', 'plan': None, 'trade_authorized': False}


def deliver(record, capture, feed, audit, *, env, clock, session=None):
    from ..agents.scheduled_review import permitted
    manual = (env.get('GITHUB_REPOSITORY') == 'Chiizzie/market-radar-ai'
              and env.get('GITHUB_REF') == 'refs/heads/phase-1/market-data-layer'
              and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
              and env.get('GITHUB_RUN_ATTEMPT') == '1')
    if (not (manual or permitted(env, clock()))
            or env.get('SEND_CANDIDATE_REVIEW') != 'true'):
        raise ValueError('manual_candidate_delivery_required')
    secret = env.get('REVIEW_INGEST_SECRET', '')
    if len(secret) < 32:
        raise ValueError('ingestion_secret_missing_or_invalid')
    body = (canonical(export_archive(record, capture, feed, audit))+'\n').encode()
    if len(body) > MAX_BYTES:
        raise ValueError('candidate_archive_too_large')
    now = clock()
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    timestamp = str(int(now.timestamp()))
    signature = hmac.new(secret.encode(), timestamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
    archive_id = hashlib.sha256(body).hexdigest()
    try:
        response = (session or requests).post(ENDPOINT, data=body,
            headers={'Content-Type':'application/json; charset=utf-8',
                     'X-Timestamp':timestamp, 'X-Signature':'sha256='+signature},
            timeout=(10,30), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError()
        value = response.json()
        if value.get('ok') is not True or value.get('archive_id') != archive_id:
            raise ValueError()
    except Exception:
        raise RuntimeError('Candidate archive delivery unconfirmed; inspect storage before retry') from None
    return {'state':'candidate_archive_delivery_confirmed','archive_id':archive_id,
            'package_id':record['package_id'],'trade_authorized':False}
