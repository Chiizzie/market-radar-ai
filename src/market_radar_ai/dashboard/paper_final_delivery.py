"""Signed paper-verdict delivery; no execution buttons or order operations."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
import hashlib,hmac
from copy import deepcopy
import requests
from ..agents.candidate_packages import canonical
from .candidate_delivery import ENDPOINT, MAX_BYTES
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore
DASHBOARD='https://pixel-perfect-replay-32614.lovable.app/opportunity'


class PaperDeliveryError(RuntimeError):
    """A bounded receipt, never a provider body, token, chat ID or exception URL."""
    def __init__(self, receipt, stage, reason, **details):
        self.receipt = deepcopy(receipt)
        self.receipt['failure'] = {'stage': stage, 'reason': reason, **details}
        self.receipt['automatic_paid_retry'] = False
        self.receipt['notification_retry_allowed'] = False
        super().__init__(f'Paper delivery failed at {stage}: {reason}; do not retry review or notification')


def transport_reason(exc):
    if isinstance(exc, requests.exceptions.ConnectTimeout): return 'connect_timeout'
    if isinstance(exc, requests.exceptions.ReadTimeout): return 'read_timeout'
    if isinstance(exc, requests.exceptions.ConnectionError): return 'connection_error'
    if isinstance(exc, requests.exceptions.Timeout): return 'timeout'
    return 'transport_error'


def response_details(reply, value):
    details = {}
    if type(reply.status_code) is int and 100 <= reply.status_code <= 599:
        details['http_status'] = reply.status_code
    if isinstance(value, dict):
        code = value.get('error_code')
        if type(code) is int and 100 <= code <= 599:
            details['provider_error_code'] = code
        params = value.get('parameters')
        delay = params.get('retry_after') if isinstance(params, dict) else None
        if type(delay) is int and 0 <= delay <= 86400:
            details['retry_after_seconds'] = delay
    return details


def render(archive, now):
    d=archive['decision'];p=d['plan']
    current=p is not None and now<datetime.fromisoformat(p['expires_at'])
    current=current and d['verdict']=='PAPER_WATCH_FOR_ENTRY'
    heading='🧪 WAIT FOR BREAKOUT — ' if current else 'ℹ️ NO PAPER ENTRY — '
    lines=[heading+d['candidate_id'], 'Simulation only • Not a live trade instruction',
           now.astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %H:%M Dublin')]
    if current:
        usd=p['native_currency']=='USD'
        rate=Decimal(p['fx_rate']) if usd else Decimal(1)
        if not rate.is_finite() or rate<=0:raise ValueError('invalid_display_fx')
        currency='USD' if usd else 'EUR';symbol='$' if usd else '€'
        def price(key):
            # Decimal conversion uses this plan's original FX, never today's FX.
            value=Decimal(p[key])/rate
            return symbol+format(value.quantize(Decimal('0.000001')),'f').rstrip('0').rstrip('.')+' '+currency
        def clock(at):
            return datetime.fromisoformat(at).astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %H:%M:%S Dublin')
        lines += ['WATCH ONLY — this message does not record an entry.',
                  'Wait for the breakout; do not enter just because this watch arrived.',
                  f"BREAKOUT TRIGGER: reference ask reaches {price('entry_eur')} or above.",
                  f"Stop {price('stop_eur')} | target {price('target_eur')}",
                  'TRIGGER EXPIRES: '+clock(p['expires_at'])+'. No qualifying trigger by then = SKIP.',
                  'The watcher must also pass fresh spread, price-gap and risk checks before recording a paper entry.',
                  'A separate PAPER ENTRY RECORDED message confirms a simulated entry; manual purchases appear under Account.',
                  f"Planned paper loss €{Decimal(p['planned_loss_eur']):.2f} / €20 limit | quantity {p['quantity']}",
                  f"Assumed round-trip costs {price('assumed_round_trip_cost_eur')} | fictional allocation {price('paper_capital_eur')}",
                  'Paper exit by '+clock(p['exit_by'])]
        if usd:lines.append('Stock levels are USD; converted from the recorded EUR plan using its original FX. Risk and P/L accounting remain EUR.')
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
    receipt={'dashboard':'not_confirmed','telegram':'not_attempted','trade_authorized':False}
    try:
        reply=transport.post(ENDPOINT,data=body,headers={'Content-Type':'application/json; charset=utf-8',
             'X-Timestamp':stamp,'X-Signature':'sha256='+signature},timeout=(10,30),allow_redirects=False)
    except Exception as exc:
        raise PaperDeliveryError(receipt,'dashboard_send',transport_reason(exc)) from None
    try:
        value=reply.json()
    except Exception:
        raise PaperDeliveryError(receipt,'dashboard_ack','invalid_json',**response_details(reply,None)) from None
    if (reply.status_code!=200 or not isinstance(value,dict)
            or value.get('ok') is not True or value.get('archive_id')!=archive_id):
        raise PaperDeliveryError(receipt,'dashboard_ack','acknowledgement_invalid',**response_details(reply,value))
    receipt.update(dashboard='paper_archive_delivery_confirmed',telegram='disabled')
    if env.get('SEND_SCHEDULED_TELEGRAM')=='true':
        receipt['telegram']='not_attempted'
        token,chat=env.get('TELEGRAM_BOT_TOKEN',''),env.get('TELEGRAM_CHAT_ID','')
        if not token or not chat.lstrip('-').isdigit():
            raise PaperDeliveryError(receipt,'telegram_prepare','credentials_missing')
        try:
            text=render(archive,clock())
        except Exception:
            raise PaperDeliveryError(receipt,'telegram_render','render_failed') from None
        key='research:'+hashlib.sha256(('paper-final:'+archive['packet_id']).encode()).hexdigest()
        try:
            ledger=ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_BUDGET_TOKEN','')))
            ledger.reserve(key)
        except Exception:
            raise PaperDeliveryError(receipt,'telegram_reserve','reservation_unconfirmed') from None
        receipt['notification_ledger']='reserved'
        for attempt in range(2):
            request_started_at=clock()
            decision=archive['decision']
            # Only ConnectTimeout proves the message was not sent. Recheck expiry
            # before that one bounded retry; never retry an ambiguous POST.
            if (attempt and decision['verdict']=='PAPER_WATCH_FOR_ENTRY'
                    and request_started_at>=datetime.fromisoformat(decision['plan']['expires_at'])):
                raise PaperDeliveryError(receipt,'telegram_send','expired_before_connect_retry')
            try:
                text=render(archive,request_started_at)
            except Exception:
                raise PaperDeliveryError(receipt,'telegram_render','render_failed') from None
            receipt['telegram_attempts']=attempt+1
            receipt['request_started_at']=request_started_at.isoformat()
            receipt['telegram']='not_confirmed'
            try:
                reply=transport.post('https://api.telegram.org/bot'+token+'/sendMessage',
                    json={'chat_id':chat,'text':text,'protect_content':True,
                          'link_preview_options':{'is_disabled':True}},timeout=(10,20),allow_redirects=False)
            except requests.exceptions.ConnectTimeout:
                receipt['telegram']='not_sent_connect_timeout'
                if attempt==0: continue
                raise PaperDeliveryError(receipt,'telegram_send','connect_timeout') from None
            except Exception as exc:
                raise PaperDeliveryError(receipt,'telegram_send',transport_reason(exc)) from None
            break
        try:
            value=reply.json()
        except Exception:
            raise PaperDeliveryError(receipt,'telegram_ack','invalid_json',**response_details(reply,None)) from None
        details=response_details(reply,value)
        if reply.status_code!=200 or not isinstance(value,dict) or value.get('ok') is not True:
            if isinstance(value,dict) and value.get('ok') is False:
                receipt['telegram']='provider_rejected'
            raise PaperDeliveryError(receipt,'telegram_ack','provider_response_not_accepted',**details)
        result=value.get('result')
        target=result.get('chat') if isinstance(result,dict) else None
        if (not isinstance(target,dict) or str(target.get('id'))!=chat
                or type(result.get('message_id')) is not int):
            raise PaperDeliveryError(receipt,'telegram_ack','acknowledgement_invalid',**details)
        acknowledged_at=clock()
        receipt['telegram']='paper_notification_confirmed'
        receipt['acknowledged_at']=acknowledged_at.isoformat()
        confirmation_failed=False
        try:
            ledger.confirm(key)
            receipt['notification_ledger']='confirmed'
        except Exception:
            confirmation_failed=True
            receipt['notification_ledger']='confirmation_unconfirmed'
        if env.get('RECORD_MANUAL_ALERT_CLOCK')=='true':
            # Failed research recording must never resend a message or paid review.
            try:
                from ..agents.manual_alert_evidence import record_ack
                from ..agents.comparison_live import EventClient
                receipt['manual_evidence']=record_ack(archive,request_started_at=request_started_at,
                    acknowledged_at=acknowledged_at,provider_date=value['result'].get('date'),
                    recorded_at=clock(),client=EventClient(secret,clock=clock))
            except Exception:
                receipt['manual_evidence']={'state':'manual_clock_unconfirmed_no_notification_retry'}
        if confirmation_failed:
            raise PaperDeliveryError(receipt,'telegram_confirm','ledger_confirmation_unconfirmed')
    return receipt
