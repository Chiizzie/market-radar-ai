"""Explicit manual delivery of one pinned historical research report, never a call."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import requests
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore
from .notification import render_review

REPORT = Path('docs/dashboard/nvda-reviewed-plan-2026-11-03.json')
REPORT_SHA256 = '20e83e396625bd7b234c7396c9f80e3c597ea06c8837922550e66989850514f7'


def execute(env, *, ledger, now, session=None, report_bytes=None):
    if (env.get('GITHUB_REPOSITORY') != 'Chiizzie/market-radar-ai'
            or env.get('GITHUB_REF') != 'refs/heads/phase-1/market-data-layer'
            or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_RUN_ATTEMPT') != '1'
            or env.get('SEND_HISTORICAL_REPORT') != 'true'):
        raise ValueError('explicit_manual_first_attempt_required')
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    chat = env.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat.lstrip('-').isdigit():
        raise ValueError('telegram_secrets_missing_or_invalid')
    raw = REPORT.read_bytes() if report_bytes is None else report_bytes
    if hashlib.sha256(raw).hexdigest() != REPORT_SHA256:
        raise ValueError('untrusted_report')
    preview = render_review(json.loads(raw), now=now)
    text = preview['text']
    if len(text.encode('utf-16-le')) // 2 > 4096:
        raise ValueError('message_too_long')
    key = preview['deduplication_key']
    ledger.reserve(key)  # Must be durable and acknowledged BEFORE the only POST.
    try:
        response = (session or requests).post(
            'https://api.telegram.org/bot' + token + '/sendMessage',
            json={'chat_id': chat, 'text': text, 'protect_content': True},
            timeout=(10, 20), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError()
        body = response.json()
        if (body.get('ok') is not True or str(body['result']['chat']['id']) != chat
                or type(body['result']['message_id']) is not int):
            raise ValueError()
        ledger.confirm(key)
    except Exception:
        raise RuntimeError('Delivery unconfirmed; reservation retained. Do not retry.') from None
    return {'state': 'historical_report_delivery_confirmed',
            'trade_authorized': False, 'automatic_notifications_enabled': False}


if __name__ == '__main__':
    try:
        ledger = DeliveryLedger(GitHubDeliveryStore(os.environ.get('GITHUB_TOKEN', '')))
        print(execute(os.environ, ledger=ledger, now=datetime.now(timezone.utc)))
    except Exception:
        raise SystemExit('Report blocked or delivery unconfirmed; no automatic retry.') from None
