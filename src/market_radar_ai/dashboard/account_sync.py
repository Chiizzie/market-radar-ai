"""Read-only Invest account mirror. Private data stays in memory, never artifacts/logs."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib, hmac, json, os, time, re
from urllib.parse import urlsplit, parse_qs
import requests

BASE = 'https://live.trading212.com'
DEST = 'https://pixel-perfect-replay-32614.lovable.app/api/public/account/ingest'
PATHS = {'/api/v0/equity/account/summary', '/api/v0/equity/positions', '/api/v0/equity/orders', '/api/v0/equity/history/orders'}
MAX_PAGES = 50


def safe_path(path):
    u=urlsplit(path)
    if u.scheme or u.netloc or u.fragment or u.path not in PATHS: raise ValueError('account_path_rejected')
    query=parse_qs(u.query,strict_parsing=True)
    if any(k not in {'limit','cursor'} or len(v)!=1 or not v[0].isdigit() for k,v in query.items()): raise ValueError('account_query_rejected')
    return path


def decimal(value):
    if value is None:return None
    d=Decimal(str(value))
    if not d.is_finite():raise ValueError('invalid_amount')
    return str(d)


def money(row, key):return decimal(row.get(key))
def instrument(row):
    v=row.get('instrument',{})
    return {'ticker':v.get('ticker') or row.get('ticker'), 'name':v.get('name'), 'currency':v.get('currency') or row.get('currency')}

def order(row):
    from .account_costs import label
    return dict(id=str(row['id']),**instrument(row),side=row['side'],status=row['status'],created_at=row['createdAt'],
                quantity=money(row,'quantity'),filled_quantity=money(row,'filledQuantity'),requested_value=money(row,'value'),
                filled_value=money(row,'filledValue'),order_currency=row.get('currency'),initiated_from=label(row.get('initiatedFrom')))


def collect(get, now, sleep=time.sleep):
    from .account_costs import extract, audit
    summary=get('/api/v0/equity/account/summary')
    if summary['currency']!='EUR':raise ValueError('account_currency_not_eur')
    investments=summary.get('investments',{});cash=summary.get('cash',{})
    positions=[]
    for r in get('/api/v0/equity/positions'):
        w=r.get('walletImpact',{})
        if w.get('currency')!='EUR':raise ValueError('position_currency_not_eur')
        positions.append(dict(**instrument(r),quantity=money(r,'quantity'),cost_eur=money(w,'totalCost'),value_eur=money(w,'currentValue'),unrealized_eur=money(w,'unrealizedProfitLoss')))
    pending=[order(r) for r in get('/api/v0/equity/orders')]
    history=[];seen=set();path='/api/v0/equity/history/orders?limit=50'
    for page in range(MAX_PAGES):
        if path in seen:raise ValueError('history_pagination_loop')
        seen.add(path);data=get(safe_path(path))
        if not isinstance(data.get('items'),list):raise ValueError('history_invalid')
        for r in data['items']:
            o=order(r['order']);f=r.get('fill');w=(f or {}).get('walletImpact') or {}
            if w and w.get('currency')!='EUR':raise ValueError('fill_currency_not_eur')
            history.append({'order':o,'fill':None if not f else {'id':str(f['id']),'filled_at':f['filledAt'],'type':f['type'],
                'quantity':money(f,'quantity'),'price_native':money(f,'price'),'net_eur':money(w,'netValue'),'realized_eur':money(w,'realisedProfitLoss'),
                'cost_evidence':extract(w)}})
        path=data.get('nextPagePath')
        if not path:break
        safe_path(path)
        if page+1<MAX_PAGES:sleep(3.1)
    return {'schema_version':'trading212-account-v1','broker':'trading212_invest','read_only':True,'generated_at':now.isoformat(),
            'account_ref':hashlib.sha256(str(summary['id']).encode()).hexdigest(),'currency':'EUR','summary':{'total_value_eur':money(summary,'totalValue'),'cash_eur':money(cash,'availableToTrade'),
            'invested_eur':money(investments,'totalCost'),'realized_eur':money(investments,'realizedProfitLoss'),'unrealized_eur':money(investments,'unrealizedProfitLoss')},
            'positions':positions,'pending_orders':pending,'history':history,'history_complete':not bool(path),
            'cost_audit':audit(history)}


class Reader:
    def __init__(self,key,secret,*,session=None,sleep=time.sleep,clock=time.time):
        self.session=session or requests.Session();self.session.auth=(key,secret)
        self.sleep,self.clock=sleep,clock
        self.stage='account_read';self.retries=0
    def __call__(self,path):
        path=safe_path(path)
        self.stage={'/api/v0/equity/account/summary':'account_summary',
                    '/api/v0/equity/positions':'positions',
                    '/api/v0/equity/orders':'pending_orders',
                    '/api/v0/equity/history/orders':'order_history'}[urlsplit(path).path]
        for attempt in range(2):
            delay=5.0
            try:
                with self.session.get(BASE+path,timeout=(10,25),allow_redirects=False,stream=True) as r:
                    if r.status_code==200:
                        body=bytearray()
                        for chunk in r.iter_content(65536):
                            body.extend(chunk)
                            if len(body)>2_000_000:raise RuntimeError('account_response_too_large')
                        try:return json.loads(body,parse_float=Decimal)
                        except (ValueError,UnicodeError):raise RuntimeError('account_read_invalid_json') from None
                    code='account_read_http_'+str(r.status_code)
                    if r.status_code not in (429,500,502,503,504):raise RuntimeError(code)
                    for header,absolute in [('Retry-After',False),('x-ratelimit-reset',True)]:
                        value=r.headers.get(header)
                        if value is None:continue
                        try:
                            wait=float(value)-(self.clock() if absolute else 0)
                            if not Decimal(str(wait)).is_finite():raise ValueError()
                            delay=max(delay,wait)
                        except (ValueError,ArithmeticError):
                            raise RuntimeError('account_read_backoff_unusable') from None
            except (requests.Timeout,requests.ConnectionError):
                code='account_read_transport_error'
            except requests.RequestException:
                raise RuntimeError('account_read_transport_error') from None
            # At most two extra GETs across the entire account import. Never
            # retry a notification, delivery POST or any broker order operation.
            if attempt or self.retries>=2:raise RuntimeError(code)
            if delay>10:raise RuntimeError('account_read_backoff_exceeds_budget')
            self.retries+=1;self.sleep(delay)


def public_error(error):
    code=str(error)
    allowed={'account_currency_not_eur','position_currency_not_eur','fill_currency_not_eur',
        'account_delivery_unconfirmed','account_read_transport_error','account_read_invalid_json',
        'account_response_too_large','account_payload_too_large','account_read_backoff_unusable',
        'account_read_backoff_exceeds_budget','history_pagination_loop','history_invalid','ingest_not_configured'}
    return code if code in allowed or re.fullmatch(r'account_read_http_[1-5][0-9]{2}',code) else 'account_sync_failed'


def deliver(payload,secret,now,post=requests.post):
    body=json.dumps(payload,separators=(',',':')).encode()
    if len(body)>1_900_000:raise ValueError('account_payload_too_large')
    stamp=str(int(now.timestamp()));sig=hmac.new(secret.encode(),stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
    r=post(DEST,data=body,headers={'Content-Type':'application/json','X-Timestamp':stamp,'X-Signature':'sha256='+sig},timeout=(10,30),allow_redirects=False)
    if r.status_code!=200 or r.json().get('ok') is not True:raise RuntimeError('account_delivery_unconfirmed')


def main():
    # Dedicated opt-in, independent of research/AI. Never dump API responses or tracebacks.
    from .collection_schedule import scheduled_scope
    if os.environ.get('ENABLE_ACCOUNT_SYNC')!='true' or not scheduled_scope(os.environ,datetime.now(timezone.utc)):return
    stage='configuration';reader=None
    try:
        key=os.environ['TRADING212_API_KEY'];secret=os.environ['TRADING212_API_SECRET'];ingest=os.environ['REVIEW_INGEST_SECRET']
        if len(ingest)<32:raise ValueError('ingest_not_configured')
        reader=Reader(key,secret);stage='account_read'
        payload=collect(reader,datetime.now(timezone.utc))
        if os.environ.get('ENABLE_POSITION_MONITOR')=='true':
            stage='position_monitor'
            from .position_monitor import collect_monitor, notify
            monitor=collect_monitor(payload,env=os.environ,now=datetime.now(timezone.utc))
            payload['position_monitor']=monitor
            try:
                monitor['notification_status']=notify(monitor,payload,env=os.environ)
            except Exception:
                monitor['notification_status']='unconfirmed'
        stage='dashboard_delivery'
        deliver(payload,ingest,datetime.now(timezone.utc))
        print('Private account sync delivered; no AI or order operations.')
    except Exception as e:
        # Allowlisted error codes only: no financial data or credentials in public logs.
        print(json.dumps({'status':'account_sync_failed','stage':reader.stage if reader and stage=='account_read' else stage,
            'code':public_error(e),'read_retries':reader.retries if reader else 0}))
        raise SystemExit(1) from None

if __name__=='__main__':main()
