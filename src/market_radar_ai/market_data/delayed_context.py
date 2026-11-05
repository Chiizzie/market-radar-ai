"""Free delayed consolidated premarket context; never execution evidence."""
from datetime import datetime,timedelta,timezone
import json,os
import requests
from .providers.alpaca import NY,SYMBOL
from .stock_context import parse_series
from .reference_quotes import digest


def fetch(symbol, *, env=None, session=None, clock=lambda:datetime.now(timezone.utc)):
    now=clock();local=now.astimezone(NY)
    if now.tzinfo is None or not SYMBOL.fullmatch(symbol):raise ValueError('invalid_context_request')
    start=local.replace(hour=4,minute=0,second=0,microsecond=0)
    end=now-timedelta(minutes=16)  # margin beyond Alpaca's free 15-minute boundary
    p={'schema_version':'delayed-stock-context-v1','symbol':symbol,'provider':'alpaca_sip_delayed',
       'native_currency':'USD','retrieved_at':now.isoformat(),'status':'unavailable',
       'trade_authorized':False,'data_delay_seconds':900,
       'intraday':{'status':'unavailable','bars':[],'request_start':start.isoformat(),'request_end':end.isoformat()}}
    if local.weekday()>=5 or local>=local.replace(hour=9,minute=30,second=0,microsecond=0) or end<=start:
        p['status']='window_not_started_or_regular_session';return {'payload':p,'payload_sha256':digest(p)}
    env=os.environ if env is None else env
    try:
        if not env.get('ALPACA_API_KEY') or not env.get('ALPACA_API_SECRET'):raise ValueError()
        with (session or requests.Session()).get(f'https://data.alpaca.markets/v2/stocks/{symbol}/bars',
            params={'timeframe':'5Min','start':start.isoformat(),'end':end.isoformat(),'feed':'sip','currency':'USD','adjustment':'raw','asof':'-','sort':'asc','limit':1000},
            headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET']},
            timeout=(5,15),allow_redirects=False,stream=True) as response:
            if response.status_code!=200:raise ValueError()
            body=bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body)>1_000_000:raise ValueError()
        data=json.loads(body)
        bars=parse_series(data,symbol=symbol,start=start,end=end,timeframe='5Min',source='alpaca_sip_delayed')
        p['intraday'].update(status='received' if bars else 'empty',bars=bars,raw_payload_sha256=digest(data))
        p['status']='received'
    except Exception:p['reason']='delayed_provider_unavailable'
    p['retrieved_at']=clock().isoformat()
    return {'payload':p,'payload_sha256':digest(p)}


def enrich_delayed(document, *, fetcher=fetch, now=None):
    now=now or datetime.now(timezone.utc);local=now.astimezone(NY)
    if local.weekday()>=5 or local>=local.replace(hour=9,minute=30,second=0,microsecond=0):return document
    symbols=[r['requested_symbol'] for r in document['captures'] if r['market']=='stocks']
    if len(symbols)>20:raise ValueError('delayed_context_universe_too_large')
    document['delayed_stock_context']=[fetcher(s) for s in symbols]
    return document
