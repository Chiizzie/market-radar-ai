"""Read-only Invest account mirror. Private data stays in memory, never artifacts/logs."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib, hmac, json, os, time
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
    return dict(id=str(row['id']),**instrument(row),side=row['side'],status=row['status'],created_at=row['createdAt'],
                quantity=money(row,'quantity'),filled_quantity=money(row,'filledQuantity'),requested_value=money(row,'value'),
                filled_value=money(row,'filledValue'),order_currency=row.get('currency'))


def collect(get, now, sleep=time.sleep):
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
                'quantity':money(f,'quantity'),'price_native':money(f,'price'),'net_eur':money(w,'netValue'),'realized_eur':money(w,'realisedProfitLoss')}})
        path=data.get('nextPagePath')
        if not path:break
        safe_path(path)
        if page+1<MAX_PAGES:sleep(3.1)
    return {'schema_version':'trading212-account-v1','broker':'trading212_invest','read_only':True,'generated_at':now.isoformat(),
            'account_ref':hashlib.sha256(str(summary['id']).encode()).hexdigest(),'currency':'EUR','summary':{'total_value_eur':money(summary,'totalValue'),'cash_eur':money(cash,'availableToTrade'),
            'invested_eur':money(investments,'totalCost'),'realized_eur':money(investments,'realizedProfitLoss'),'unrealized_eur':money(investments,'unrealizedProfitLoss')},
            'positions':positions,'pending_orders':pending,'history':history,'history_complete':not bool(path)}


class Reader:
    def __init__(self,key,secret):
        self.session=requests.Session();self.session.auth=(key,secret)
    def __call__(self,path):
        try:
            with self.session.get(BASE+safe_path(path),timeout=(10,25),allow_redirects=False,stream=True) as r:
                if r.status_code!=200:raise RuntimeError('account_read_http_'+str(r.status_code))
                body=bytearray()
                for chunk in r.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>2_000_000:raise RuntimeError('account_response_too_large')
                return json.loads(body,parse_float=Decimal)
        except requests.RequestException:raise RuntimeError('account_read_transport_error') from None


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
    try:
        key=os.environ['TRADING212_API_KEY'];secret=os.environ['TRADING212_API_SECRET'];ingest=os.environ['REVIEW_INGEST_SECRET']
        if len(ingest)<32:raise ValueError('ingest_not_configured')
        payload=collect(Reader(key,secret),datetime.now(timezone.utc))
        deliver(payload,ingest,datetime.now(timezone.utc))
        print('Private account sync delivered; no AI or order operations.')
    except Exception as e:
        # Allowlisted error codes only: no financial data or credentials in public logs.
        code=str(e)
        allowed={'account_currency_not_eur','position_currency_not_eur','fill_currency_not_eur','account_delivery_unconfirmed'}
        if code not in allowed and not (code.startswith('account_read_http_') and code[18:].isdigit()):code='account_sync_failed'
        print(code)
        raise SystemExit(1) from None

if __name__=='__main__':main()
