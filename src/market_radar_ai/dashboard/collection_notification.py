"""Hourly, zero-model collection status. Separate from research/trade alerts."""
from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo
import requests
from .collection_schedule import scheduled_scope
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore


def notify(report, *, env, clock, ledger=None, session=None):
    if env.get('SEND_COLLECTION_TELEGRAM')!='true':return {'state':'disabled'}
    now=clock()
    if not scheduled_scope(env,now):raise ValueError('collection_notice_scope')
    token,chat=env.get('TELEGRAM_BOT_TOKEN',''),env.get('TELEGRAM_CHAT_ID','')
    if not token or not chat.lstrip('-').isdigit():raise ValueError('telegram_secrets_missing_or_invalid')
    delivered=report.get('delivery',{}).get('state')=='scanner_snapshot_delivery_confirmed'
    category='delivered' if delivered else 'failed'
    local=now.astimezone(ZoneInfo('Europe/Dublin'))
    key='research:'+sha256(('collection-status-v1:'+local.strftime('%Y-%m-%dT%H%z')+':'+category).encode()).hexdigest()
    ledger=ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_PAPER_TOKEN','')))
    try:ledger.reserve(key)
    except ValueError as exc:
        if str(exc)=='delivery_already_attempted_do_not_retry':return {'state':'collection_notice_already_attempted'}
        raise
    lines=['ℹ️ NO ACTION — collection update' if delivered else '⚠️ SCANNER FAILURE — check required',
           'Market Radar AI • Paper/research only',local.strftime('%d %b %H:%M Dublin'),
           'Dashboard capture delivered.' if delivered else 'Collection failed. No new dashboard delivery confirmed.',
           ('Final AI review is enabled only for qualified setups. This update used no AI.'
            if env.get('AI_FINAL_REVIEW_ENABLED')=='true' else
            'Paid AI is paused. This is a free operational update, not a trade call.')]
    if delivered:
        for market,counts in report['delivery'].get('coverage',{}).items():
            lines.append(f"{market.title()}: {counts['current']}/{counts['attempted']} current; {counts['unusable_or_stale']} unavailable/stale.")
    lines+=['Status updates: at most one success and one failure notice per hour.',
            'https://pixel-perfect-replay-32614.lovable.app/scanner']
    try:
        response=(session or requests).post('https://api.telegram.org/bot'+token+'/sendMessage',
            json={'chat_id':chat,'text':'\n'.join(lines),'protect_content':True,'link_preview_options':{'is_disabled':True}},
            timeout=(10,20),allow_redirects=False)
        body=response.json()
        if response.status_code!=200 or body.get('ok') is not True or str(body['result']['chat']['id'])!=chat or type(body['result']['message_id']) is not int:raise ValueError()
        ledger.confirm(key)
    except Exception:raise RuntimeError('Collection Telegram delivery unconfirmed; do not retry') from None
    return {'state':'telegram_collection_status_confirmed','category':category,'model_calls':0}
