"""At-most-once notifications for persisted paper entries and outcomes only."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
import hashlib
import requests
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore

DASHBOARD='https://pixel-perfect-replay-32614.lovable.app/journal'


def render(row):
    o=row['outcome']; closed=row['state']=='closed'
    heading='🧪 PAPER RESULT — ' if closed else '🧪 PAPER ENTRY RECORDED — ' if row['state']=='open_simulation' else '⚠️ PAPER EXIT UNRESOLVED — '
    lines=[heading+row['symbol'],'Simulation only • No live order',
           'Entry '+datetime.fromisoformat(o['entry_at']).astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %H:%M:%S Dublin'),
           'Observed entry €'+o['entry_fill']]
    if closed:
        pnl=Decimal(o['net_pnl_eur'])
        lines += ['Exit '+datetime.fromisoformat(o['exit_at']).astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %H:%M:%S Dublin'),
                  'Observed exit €'+o['exit_fill'],f'Paper P/L after assumed costs: {pnl:+.2f} EUR',
                  'Reason: '+o['reason'].replace('_',' ')]
    elif row['state']=='unresolved':
        lines += ['No valid exit quote was observed before the cutoff. Profit/loss is unknown.']
    lines += ['Reference prices and assumed fills; not broker execution.',DASHBOARD]
    return '\n'.join(lines)


def notify(report, *, env, now, ledger=None, session=None, seen=None):
    if env.get('SEND_PAPER_LIFECYCLE_TELEGRAM')!='true': return {'sent':0,'unconfirmed':0}
    token,chat=env.get('TELEGRAM_BOT_TOKEN',''),env.get('TELEGRAM_CHAT_ID','')
    if not token or not chat.lstrip('-').isdigit(): raise ValueError('telegram_credentials_missing')
    ledger=ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_PAPER_TOKEN','')))
    seen=seen if seen is not None else set()
    transport=session or requests; result={'sent':0,'unconfirmed':0}
    for row in report['trades']:
        if row['state'] not in ('open_simulation','closed','unresolved'): continue
        entry=datetime.fromisoformat(row['outcome']['entry_at'])
        if entry.astimezone(ZoneInfo('Europe/Dublin')).date()!=now.astimezone(ZoneInfo('Europe/Dublin')).date(): continue
        key='research:'+hashlib.sha256(('paper-lifecycle-v1:'+row['packet_id']+':'+row['state']).encode()).hexdigest()
        if key in seen: continue
        try: ledger.reserve(key)
        except ValueError as exc:
            if str(exc)=='delivery_already_attempted_do_not_retry':
                seen.add(key); continue
            raise
        except RuntimeError:
            seen.add(key); result['unconfirmed']+=1; continue
        seen.add(key)
        try:
            reply=transport.post('https://api.telegram.org/bot'+token+'/sendMessage',
                json={'chat_id':chat,'text':render(row),'protect_content':True,
                      'link_preview_options':{'is_disabled':True}},timeout=(5,10),allow_redirects=False)
            value=reply.json()
            if reply.status_code!=200 or value.get('ok') is not True or str(value['result']['chat']['id'])!=chat or type(value['result']['message_id']) is not int:
                raise ValueError('telegram_acknowledgement_invalid')
            ledger.confirm(key); result['sent']+=1
        except Exception:
            result['unconfirmed']+=1  # Reservation survives: never resend an uncertain message.
    return result
