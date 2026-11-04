"""One durable Telegram notification per completed scheduled research package."""
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from .candidate_delivery import export_archive
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore

DASHBOARD = 'https://pixel-perfect-replay-32614.lovable.app/candidate-research'


def render(archive, record, audit, now):
    result = audit['result']
    expired = now >= datetime.fromisoformat(result['evidence_expires_at'])
    final = result['reviews'][-1]
    lines = ['ℹ️ NO ACTION — Market Radar AI',
             'Research only • No approved trade • Paper only',
             now.astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %H:%M Dublin'),
             'EXPIRED EVIDENCE — historical review' if expired else 'Context review — execution checks still required',
             record['package'].get('research_mode', archive['candidate_id']).replace('_', ' ')]
    decisions = final.get('symbol_decisions', [])
    if decisions:
        for d in decisions:
            lines.append(f"{d['symbol']}: {d['posture'].replace('_', ' ')}")
    else:
        lines.append(archive['candidate_id'] + ': ' + final['verdict'].replace('_', ' '))
    lines += [final['rationale'][:600], 'Open the dashboard for conditions, invalidation and evidence:', DASHBOARD]
    text = '\n'.join(lines)
    if len(text.encode('utf-16-le')) // 2 > 4096:
        raise ValueError('notification_too_long')
    return text


def deliver(record, capture, feed, audit, *, env, clock, ledger=None, session=None):
    from ..agents.scheduled_review import permitted
    if env.get('SEND_SCHEDULED_TELEGRAM') != 'true':
        return {'state': 'disabled'}
    now = clock()
    if not permitted(env, now):
        raise ValueError('notification_outside_scheduled_scope')
    token, chat = env.get('TELEGRAM_BOT_TOKEN', ''), env.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat.lstrip('-').isdigit():
        raise ValueError('telegram_secrets_missing_or_invalid')
    archive = export_archive(record, capture, feed, audit)
    text = render(archive, record, audit, now)
    ledger = ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_BUDGET_TOKEN', '')))
    key = 'research:' + archive['package_id']
    ledger.reserve(key)  # Persist before POST; uncertain deliveries are never retried.
    try:
        response = (session or requests).post('https://api.telegram.org/bot' + token + '/sendMessage',
            json={'chat_id': chat, 'text': text, 'protect_content': True,
                  'link_preview_options': {'is_disabled': True}},
            timeout=(10, 20), allow_redirects=False)
        body = response.json()
        if (response.status_code != 200 or body.get('ok') is not True
                or str(body['result']['chat']['id']) != chat
                or type(body['result']['message_id']) is not int):
            raise ValueError()
        ledger.confirm(key)
    except Exception:
        raise RuntimeError('Telegram delivery unconfirmed; do not retry') from None
    return {'state': 'telegram_research_delivery_confirmed', 'trade_authorized': False,
            'package_id': archive['package_id']}


def notify_pause(reason, *, env, clock, ledger=None, session=None):
    """One non-AI operational notice per day/reason; never a trade/review result."""
    from hashlib import sha256
    from ..agents.scheduled_review import permitted
    reasons={'quota_or_budget_deferred':'AI review paused: the remaining spending allowance is below the reserve needed for another review.',
             'daily_review_quota_reached':'AI review paused: today’s permitted review slots have been used.'}
    now=clock()
    if reason not in reasons or env.get('SEND_SCHEDULED_TELEGRAM')!='true':return {'state':'disabled'}
    if not permitted(env,now):raise ValueError('notification_outside_scheduled_scope')
    token,chat=env.get('TELEGRAM_BOT_TOKEN',''),env.get('TELEGRAM_CHAT_ID','')
    if not token or not chat.lstrip('-').isdigit():raise ValueError('telegram_secrets_missing_or_invalid')
    day=now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
    key='research:'+sha256(('operational-pause-v1:'+day+':'+reason).encode()).hexdigest()
    ledger=ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_BUDGET_TOKEN','')))
    try:ledger.reserve(key)
    except ValueError as e:
        if str(e)=='delivery_already_attempted_do_not_retry':return {'state':'pause_notice_already_attempted'}
        raise
    text='\n'.join(['ℹ️ STATUS — Market Radar AI',now.astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %H:%M Dublin'),reasons[reason],
        'No new AI review or trade call was produced by this run. Scheduled data collection is separate; this notice does not confirm its success.',DASHBOARD])
    try:
        response=(session or requests).post('https://api.telegram.org/bot'+token+'/sendMessage',
            json={'chat_id':chat,'text':text,'protect_content':True,'link_preview_options':{'is_disabled':True}},
            timeout=(10,20),allow_redirects=False)
        body=response.json()
        if response.status_code!=200 or body.get('ok') is not True or str(body['result']['chat']['id'])!=chat or type(body['result']['message_id']) is not int:raise ValueError()
        ledger.confirm(key)
    except Exception:raise RuntimeError('Telegram pause notice unconfirmed; do not retry') from None
    return {'state':'telegram_pause_notice_confirmed','trade_authorized':False}
