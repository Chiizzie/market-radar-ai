"""Signed paper-verdict delivery; no execution buttons or order operations."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,hmac
import requests
from ..agents.candidate_packages import canonical
from .candidate_delivery import ENDPOINT, MAX_BYTES
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore
from .scheduled_notification import DASHBOARD


def render(archive, now):
    d=archive['decision'];p=d['plan']
    current=p is not None and now<datetime.fromisoformat(p['expires_at'])
    heading='🧪 PAPER WATCH — ' if current and d['verdict']=='PAPER_WATCH_FOR_ENTRY' else 'ℹ️ NO PAPER ENTRY — '
    lines=[heading+d['candidate_id'], 'Simulation only • Not a live trade instruction',
           now.astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %H:%M Dublin')]
    if current:
        lines += [f"EUR entry {p['entry_eur']} | stop {p['stop_eur']} | target {p['target_eur']}",
                  f"Planned paper loss €{p['planned_loss_eur']} | quantity {p['quantity']}",
                  'Expires '+p['expires_at']+' | exit by '+p['exit_by'],p['trigger']]
    else:lines.append('No current approved paper entry. '+', '.join(d['blockers']))
    lines += ['Assumed costs and fictional allocation; broker execution permission is not verified.',DASHBOARD]
    return '\n'.join(lines)


def deliver(archive, *, env, clock, session=None, ledger=None):
    from ..agents.scheduled_review import permitted
    if not permitted(env,clock()) or env.get('SEND_CANDIDATE_REVIEW')!='true':
        raise ValueError('paper_delivery_scope')
    if archive['schema_version']!='paper-decision-archive-v1' or archive['trade_authorized'] is not False:
        raise ValueError('paper_archive_scope')
    secret=env.get('REVIEW_INGEST_SECRET','')
    if len(secret)<32:raise ValueError('ingestion_secret_missing')
    body=(canonical(archive)+'\n').encode()
    if len(body)>MAX_BYTES:raise ValueError('paper_archive_too_large')
    stamp=str(int(clock().timestamp()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
    archive_id=hashlib.sha256(body).hexdigest()
    transport=session or requests
    try:
        reply=transport.post(ENDPOINT,data=body,headers={'Content-Type':'application/json; charset=utf-8',
             'X-Timestamp':stamp,'X-Signature':'sha256='+signature},timeout=(10,30),allow_redirects=False)
        value=reply.json()
        if reply.status_code!=200 or value.get('ok') is not True or value.get('archive_id')!=archive_id:raise ValueError()
    except Exception:raise RuntimeError('Paper archive delivery unconfirmed; do not repeat review') from None
    receipt={'dashboard':'paper_archive_delivery_confirmed','telegram':'disabled','trade_authorized':False}
    if env.get('SEND_SCHEDULED_TELEGRAM')=='true':
        token,chat=env.get('TELEGRAM_BOT_TOKEN',''),env.get('TELEGRAM_CHAT_ID','')
        if not token or not chat.lstrip('-').isdigit():raise ValueError('telegram_credentials_missing')
        ledger=ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_BUDGET_TOKEN','')))
        key='research:'+hashlib.sha256(('paper-final:'+archive['packet_id']).encode()).hexdigest()
        ledger.reserve(key)
        try:
            reply=transport.post('https://api.telegram.org/bot'+token+'/sendMessage',
                json={'chat_id':chat,'text':render(archive,clock()),'protect_content':True,
                      'link_preview_options':{'is_disabled':True}},timeout=(10,20),allow_redirects=False)
            value=reply.json()
            if reply.status_code!=200 or value.get('ok') is not True or str(value['result']['chat']['id'])!=chat or type(value['result']['message_id']) is not int:raise ValueError()
            ledger.confirm(key)
        except Exception:raise RuntimeError('Paper Telegram delivery unconfirmed; do not retry') from None
        receipt['telegram']='paper_notification_confirmed'
    return receipt
