"""Hourly, zero-model collection status. Separate from research/trade alerts."""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo
import requests
from .collection_schedule import scheduled_scope
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore


class CollectionNoticeError(RuntimeError):
    def __init__(self, code):
        self.diagnostic_code = code
        super().__init__('Collection Telegram delivery unconfirmed; do not retry ['+code+']')


def review_status(report, env, now):
    if env.get('AI_FINAL_REVIEW_ENABLED') != 'true':
        return 'Paid AI is paused. This collection used no AI.'
    from .api_budget import validate_summary
    from .execution_readiness import PROTOCOL

    try:
        usage = validate_summary(report.get('api_budget'), now=now)
    except (TypeError, ValueError):
        usage = None
    if not usage or usage['status'] != 'available':
        return 'Current AI review allowance could not be verified. This collection used no AI.'
    required = PROTOCOL['budget_headroom_microeur']
    euro = Decimal(1_000_000)
    blocked = [f"{period} €{Decimal(row['remaining_microeur']) / euro:f}"
               for period, row in usage['periods'].items() if row['remaining_microeur'] < required]
    if blocked:
        return (f"Paid reviews paused at capture. Remaining allowance ({', '.join(blocked)}) "
                f"is below the €{Decimal(required) / euro:f} required for a review.")
    return 'Paid review requires a qualified setup. This collection used no AI.'


def notify(report, *, env, clock, ledger=None, session=None):
    if env.get('SEND_COLLECTION_TELEGRAM')!='true':return {'state':'disabled'}
    now=clock()
    if not scheduled_scope(env,now):raise ValueError('collection_notice_scope')
    token,chat=env.get('TELEGRAM_BOT_TOKEN',''),env.get('TELEGRAM_CHAT_ID','')
    if not token or not chat.lstrip('-').isdigit():raise ValueError('telegram_secrets_missing_or_invalid')
    delivery = report.get('delivery', {})
    delivered = delivery.get('state') == 'scanner_snapshot_delivery_confirmed'
    unconfirmed = delivery.get('state') == 'scanner_snapshot_delivery_unconfirmed'
    opening_text = []
    late = delivered and delivery.get('acknowledged_before_expiry') is False
    if delivered and not late and report.get('opening_session'):
        from .opening_brief import lines as opening_lines, waiting_for_opening_update
        try:
            brief = report['opening_session']
            if waiting_for_opening_update(brief, now):
                return {'state':'collection_notice_waiting_for_opening_checkpoint','model_calls':0}
            opening_text = opening_lines(brief, now)
        except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
            opening_text = ['Opening evidence unavailable for this capture.']
    category='delivered' if delivered else 'failed'
    local=now.astimezone(ZoneInfo('Europe/Dublin'))
    key='research:'+sha256(('collection-status-v1:'+local.strftime('%Y-%m-%dT%H%z')+':'+category).encode()).hexdigest()
    ledger=ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_PAPER_TOKEN','')))
    try:ledger.reserve(key)
    except ValueError as exc:
        if str(exc)=='delivery_already_attempted_do_not_retry':return {'state':'collection_notice_already_attempted'}
        raise
    lines=['ℹ️ COLLECTION UPDATE' if delivered else '⚠️ SCANNER FAILURE — check required',
           'Market Radar AI • Paper/research only', local.strftime('%d %b %H:%M Dublin'),
           'Dashboard capture delivered.' if delivered else 'Collection failed. No new dashboard delivery confirmed.']
    if late:
        lines[3] = 'Dashboard capture delivered. Its acknowledgement arrived after expiry. Paper review skipped for this scan.'
    if unconfirmed:
        reason = delivery.get('reason')
        if reason in ('connect_timeout', 'read_timeout', 'timeout'):
            detail = 'Dashboard acknowledgement timed out.'
        elif reason == 'http_status':
            detail = f"Dashboard returned HTTP {delivery['http_status']}."
        else:
            detail = 'Dashboard acknowledgement could not be verified.'
        lines[3] = f'Market data collected. {detail} Paper review skipped for this scan.'
    if delivered and not late:
        lines.append(review_status(report, env, now))
    if opening_text:
        lines[0] = 'ℹ️ OPENING UPDATE — paper research'
        lines.extend(opening_text)
    if delivered or unconfirmed:
        for market,counts in delivery.get('coverage',{}).items():
            lines.append(f"{market.title()}: {counts['current']}/{counts['attempted']} current; {counts['unusable_or_stale']} unavailable/stale.")
    lines+=['Status updates: at most one success and one failure notice per hour.',
            'https://pixel-perfect-replay-32614.lovable.app/scanner']
    reason='telegram_transport_unconfirmed'
    try:
        response=(session or requests).post('https://api.telegram.org/bot'+token+'/sendMessage',
            json={'chat_id':chat,'text':'\n'.join(lines),'protect_content':True,'link_preview_options':{'is_disabled':True}},
            timeout=(10,20),allow_redirects=False)
        reason='telegram_http_'+str(int(response.status_code))
        body=response.json()
        if response.status_code!=200 or body.get('ok') is not True or str(body['result']['chat']['id'])!=chat or type(body['result']['message_id']) is not int:raise ValueError()
    except Exception:raise CollectionNoticeError(reason) from None
    try:
        ledger.confirm(key)
    except (RuntimeError, ValueError, KeyError):
        # Telegram acknowledged the message. Preserve the reservation and disclose
        # the accounting gap; a failed acknowledgement write must never resend it.
        return {'state':'telegram_collection_sent_confirmation_pending','category':category,
                'diagnostic_code':'notification_ledger_confirmation_unavailable','model_calls':0}
    return {'state':'telegram_collection_status_confirmed','category':category,'model_calls':0}


def operational_notice(report, *, env, clock):
    """An optional status-message failure does not erase collection success."""
    try:
        receipt = notify(report, env=env, clock=clock)
    except (RuntimeError, ValueError, KeyError) as exc:
        code = getattr(exc, 'diagnostic_code', 'notification_ledger_or_configuration_unavailable')
        receipt = {'state':'collection_notice_unconfirmed','diagnostic_code':code,
                   'retry_allowed':False,'model_calls':0}
    if receipt['state'] in ('collection_notice_unconfirmed','telegram_collection_sent_confirmation_pending'):
        from pathlib import Path
        message='Optional collection status message needs attention: '+receipt['diagnostic_code']+'. No automatic resend.'
        print('::warning::'+message)
        if env.get('GITHUB_STEP_SUMMARY'):
            with Path(env['GITHUB_STEP_SUMMARY']).open('a') as f:f.write('\n- '+message+'\n')
    return receipt
