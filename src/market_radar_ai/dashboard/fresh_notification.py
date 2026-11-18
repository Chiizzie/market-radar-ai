"""Deliver only a newly completed, independently revalidated research review."""
from datetime import timedelta
import requests
from .plan_review import export_review, aware
from .notification import render_review


def deliver(capture, catalogue, draft, audit, *, env, ledger, clock, session=None):
    if (env.get('GITHUB_REPOSITORY') != 'Chiizzie/market-radar-ai'
            or env.get('GITHUB_REF') != 'refs/heads/phase-1/market-data-layer'
            or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_RUN_ATTEMPT') != '1'
            or env.get('PLAN_REVIEW_MODE') != 'paid'
            or env.get('SEND_FRESH_REVIEW') != 'true'):
        raise ValueError('fresh_delivery_requires_explicit_manual_paid_review')
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    chat = env.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat.lstrip('-').isdigit():
        raise ValueError('telegram_secrets_missing_or_invalid')
    now = clock()
    # Reconstruct from source evidence + audited responses, never trust an
    # uploaded dashboard JSON or a pre-rendered notification as authorization.
    review = export_review(capture, catalogue, draft, audit, now=now)
    expiry = aware(review['expires_at'])
    completed = aware(review['review_completed_at'])
    def fresh(t):
        if t.tzinfo is None or not completed <= t < expiry - timedelta(seconds=30):
            raise ValueError('insufficient_delivery_freshness')
        if t - completed > timedelta(minutes=2):
            raise ValueError('review_too_old_for_notification')
    fresh(now)
    preview = render_review(review, now=now)
    if len(preview['text'].encode('utf-16-le')) // 2 > 4096:
        raise ValueError('message_too_long')
    key = preview['deduplication_key']
    ledger.reserve(key)
    # Reservation can be slow. Recheck immediately before the sole POST.
    fresh(clock())
    try:
        response = (session or requests).post(
            'https://api.telegram.org/bot' + token + '/sendMessage',
            json={'chat_id': chat, 'text': preview['text'], 'protect_content': True},
            timeout=(10, 20), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError()
        body = response.json()
        if (body.get('ok') is not True or str(body['result']['chat']['id']) != chat
                or type(body['result']['message_id']) is not int):
            raise ValueError()
        ledger.confirm(key)
    except Exception:
        raise RuntimeError('Fresh delivery unconfirmed; do not retry.') from None
    return {'state': 'fresh_research_delivery_confirmed', 'snapshot_id': review['snapshot_id'],
            'trade_authorized': False, 'expires_at': review['expires_at']}
