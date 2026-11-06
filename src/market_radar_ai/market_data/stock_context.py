"""Historical and extended-hours stock context, separate from fresh trade evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from zoneinfo import ZoneInfo
import requests

from .models import Candle
from .providers.alpaca import SYMBOL, NY
from .reference_quotes import digest


def parse_series(data, *, symbol, start, end, timeframe, source="alpaca_iex"):
    if not isinstance(data, dict) or data.get('symbol') != symbol or data.get('next_page_token'):
        raise ValueError('identity_or_pagination')
    if 'bars' not in data or (data['bars'] is not None and not isinstance(data['bars'], list)):
        raise ValueError('invalid_bars')
    rows, previous = [], None
    raw = data['bars'] or []
    if len(raw) > 1000:
        raise ValueError('too_many_bars')
    for bar in raw:
        at = datetime.fromisoformat(bar['t'].replace('Z', '+00:00'))
        if at.tzinfo is None or not start <= at <= end or (previous and at <= previous):
            raise ValueError('bar_time_invalid')
        previous = at
        if timeframe == '1Day':
            # Today's aggregate is incomplete, even if regular trading has closed.
            if at.astimezone(NY).date() >= end.astimezone(NY).date():
                continue
        else:
            if at.second or at.microsecond or at.minute % 5:
                raise ValueError('unaligned_bar')
            if at+timedelta(minutes=5) > end:
                continue
        values = {k: Decimal(str(bar[v])) for k, v in
                  [('open','o'),('high','h'),('low','l'),('close','c'),('volume','v')]}
        if not all(v.is_finite() for v in values.values()):
            raise ValueError('nonfinite_bar')
        c = Candle(symbol=symbol, interval='1d' if timeframe=='1Day' else '5m',
                   timestamp=at, quote_currency='USD', source=source, **values)
        rows.append(c.model_dump(mode='json'))
    return rows[-10:] if timeframe=='1Day' else rows[-24:]


def fetch_context(symbol, *, session=None, env=None, clock=lambda: datetime.now(timezone.utc)):
    now = clock()
    if now.tzinfo is None or not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise ValueError('invalid_context_request')
    env = os.environ if env is None else env
    transport = session or requests.Session()
    local = now.astimezone(NY)
    windows = {'daily': ('1Day', (local-timedelta(days=21)).replace(hour=0,minute=0,second=0,microsecond=0)),
               'intraday': ('5Min', local.replace(hour=4,minute=0,second=0,microsecond=0))}
    output = {'schema_version':'stock-context-capture-v1', 'symbol':symbol,
        'provider':'alpaca_iex', 'native_currency':'USD', 'retrieved_at':None,
        'status':'partial', 'trade_authorized':False}
    for kind, (frame, start) in windows.items():
        section = {'status':'unavailable','bars':[], 'request_start':start.isoformat(), 'request_end':now.isoformat()}
        output[kind] = section
        if now <= start:
            section['status'] = 'window_not_started'
            continue
        try:
            key, secret = env.get('ALPACA_API_KEY'), env.get('ALPACA_API_SECRET')
            if not key or not secret:
                section['reason'] = 'credentials_missing'
                continue
            with transport.get(f'https://data.alpaca.markets/v2/stocks/{symbol}/bars',
                    params={'timeframe':frame,'start':start.isoformat(),'end':now.isoformat(),
                            'feed':'iex','currency':'USD','adjustment':'raw','asof':'-',
                            'sort':'asc','limit':1000},
                    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},
                    timeout=(5,15), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise ValueError('http_error')
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>1_000_000:
                        raise ValueError('body_too_large')
            data = json.loads(body)
            bars = parse_series(data, symbol=symbol,start=start,end=now,timeframe=frame)
            section.update(status='received' if bars else 'empty', bars=bars,
                           raw_payload_sha256=digest(data))
        except Exception:
            section['reason'] = 'provider_or_payload_unavailable'
    output['retrieved_at'] = clock().isoformat()
    if all(output[k]['status'] in ('received','empty','window_not_started') for k in windows):
        output['status'] = 'received'
    return {'payload':output, 'payload_sha256':digest(output)}


def enrich(document, *, fetch=fetch_context):
    result = deepcopy(document)
    symbols = list(dict.fromkeys(c['requested_symbol'] for c in document['captures'] if c['market']=='stocks'))
    if len(symbols)>20:
        raise ValueError('context_universe_too_large')
    result['stock_context'] = [fetch(symbol) for symbol in symbols]
    return result


def connectivity_exit_code(document):
    # A single unsupported symbol is a visible data gap, not a batch outage.
    rows = document['stock_context']
    return int(bool(rows) and all(all(r['payload'][k]['status'] == 'unavailable'
               for k in ('daily', 'intraday')) for r in rows))


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.capture.stat().st_size>4_000_000:
        raise ValueError('input_too_large')
    result = enrich(json.loads(args.capture.read_text()))
    if os.environ.get('ENABLE_DELAYED_PREMARKET') == 'true':
        from .delayed_context import enrich_delayed
        result = enrich_delayed(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'stock_context':[{'symbol':r['payload']['symbol'],
        'daily':r['payload']['daily']['status'],'intraday':r['payload']['intraday']['status']}
        for r in result['stock_context']], 'model_calls':0,'trade_authorized':False}))
    return connectivity_exit_code(result)


if __name__=='__main__':
    raise SystemExit(main())
