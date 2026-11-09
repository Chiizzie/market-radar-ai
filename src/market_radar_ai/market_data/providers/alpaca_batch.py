"""Bounded IEX batch reads; pagination and identity gaps never count as coverage."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import requests
from .alpaca import NY, SYMBOL, parse_bars
from ..models import ProviderResult, ValidationIssue


def read(path, params, *, env, session, max_bytes=8_000_000):
    key, secret = env.get('ALPACA_API_KEY'), env.get('ALPACA_API_SECRET')
    if not key or not secret:
        raise ValueError('credentials_missing')
    with session.get('https://data.alpaca.markets/v2/stocks/'+path, params=params,
            headers={'APCA-API-KEY-ID':key, 'APCA-API-SECRET-KEY':secret},
            timeout=(5,15), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError('batch_http_failure')
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body)>max_bytes:
                raise ValueError('batch_response_too_large')
    result = json.loads(body)
    if not isinstance(result, dict):
        raise ValueError('invalid_batch_payload')
    return result


def symbols_checked(symbols, maximum):
    symbols=list(symbols)
    if (not 1<=len(symbols)<=maximum or len(set(symbols))!=len(symbols)
            or any(not isinstance(s,str) or not SYMBOL.fullmatch(s) for s in symbols)):
        raise ValueError('invalid_batch_symbols')
    return symbols


def raw_bars(symbols, *, start, end, frame, env, session):
    symbols=symbols_checked(symbols,100)
    params={'symbols':','.join(symbols), 'timeframe':frame,
        'start':start.isoformat(),'end':end.isoformat(),'feed':'iex','currency':'USD',
        'adjustment':'raw','asof':'-','sort':'asc','limit':10000}
    output,tokens={},set()
    for _ in range(5):
        data=read('bars',params,env=env,session=session)
        rows=data.get('bars')
        if (not isinstance(rows,dict) or set(rows)-set(symbols)
                or any(not isinstance(v,list) for v in rows.values())):
            raise ValueError('batch_bar_identity_or_shape')
        for symbol,bars in rows.items():output.setdefault(symbol,[]).extend(bars)
        if sum(len(v) for v in output.values())>10000:
            raise ValueError('batch_bar_capacity')
        token=data.get('next_page_token')
        if not token:return output
        if not isinstance(token,str) or len(token)>1000 or token in tokens:
            raise ValueError('batch_pagination_incomplete')
        tokens.add(token);params={**params,'page_token':token}
    # An incomplete page cannot establish that other symbols had no bars.
    raise ValueError('batch_pagination_incomplete')


def fetch_histories(symbols, *, env, session=None, clock=lambda:datetime.now(timezone.utc)):
    from ..limits import STOCK_SCREEN_LIMIT
    symbols=symbols_checked(symbols,STOCK_SCREEN_LIMIT)
    now=clock()
    if now.tzinfo is None:raise ValueError('aware_clock_required')
    local=now.astimezone(NY)
    start=local.replace(hour=9,minute=30,second=0,microsecond=0)
    end=min(now,local.replace(hour=16,minute=0,second=0,microsecond=0))
    def unavailable(symbol, code, status='error'):
        return ProviderResult(provider='alpaca_iex',retrieved_at=clock(),status=status,
            issues=[ValidationIssue(code=code,message='Batch IEX observation unavailable',symbol=symbol)])
    if local.weekday()>=5 or end<=start:
        return {s:unavailable(s,'regular_session_not_started','ok') for s in symbols}
    if end<start+timedelta(minutes=5):
        return {s:unavailable(s,'regular_session_warmup','ok') for s in symbols}
    from concurrent.futures import ThreadPoolExecutor
    def fetch_batch(batch):
        # One session per concurrent batch; injected transports remain serial.
        transport=session or requests.Session()
        output={}
        try:
            try:
                rows=raw_bars(batch,start=start,end=end,frame='5Min',env=env,session=transport)
            except Exception:
                return {s:unavailable(s,'batch_unavailable_or_incomplete') for s in batch}
            received=clock()
            for symbol in batch:
                try:
                    output[symbol]=parse_bars({'symbol':symbol,'bars':rows.get(symbol,[])},
                        symbol=symbol,start=start,end=end,received=received)
                except Exception:
                    output[symbol]=unavailable(symbol,'invalid_batch_symbol_payload')
            return output
        finally:
            if session is None: transport.close()
    batches=[symbols[i:i+100] for i in range(0,len(symbols),100)]
    with ThreadPoolExecutor(max_workers=1 if session is not None else 4) as executor:
        return {s:r for batch in executor.map(fetch_batch,batches) for s,r in batch.items()}


def discover_snapshots(symbols, *, env, now, session=None, prior_snapshots=None,
                       clock=lambda:datetime.now(timezone.utc)):
    """Rank fresh catalogue trades by relative activity and recent acceleration.

    IEX is a partial exchange feed. Receipt is not exchange freshness, and a
    catalogue listing is not an account permission or a technical check.
    """
    if now.tzinfo is None:raise ValueError('aware_clock_required')
    symbols=symbols_checked(symbols,20000)
    transport=session or requests.Session()
    from ..discovery_signals import measurements
    received,fresh,scores=set(),set(),{}
    evidence = {s: {'snapshot_status': 'not_received'} for s in symbols}
    checkpoint = {}
    failures=0
    for offset in range(0,len(symbols),500):
        batch=symbols[offset:offset+500]
        try:
            data=read('snapshots',{'symbols':','.join(batch),'feed':'iex'},env=env,session=transport)
            if set(data)-set(batch):raise ValueError('unexpected_snapshot_identity')
        except Exception:
            failures+=1
            for symbol in batch: evidence[symbol]['snapshot_status'] = 'batch_unavailable'
            continue
        evaluated=clock()
        for symbol,row in data.items():
            if not isinstance(row,dict):
                evidence[symbol]['snapshot_status'] = 'invalid_snapshot'
                continue
            received.add(symbol)
            evidence[symbol]['snapshot_status'] = 'invalid_snapshot'
            try:
                trade,daily,previous=row['latestTrade'],row['dailyBar'],row['prevDailyBar']
                at=datetime.fromisoformat(trade['t'].replace('Z','+00:00'))
                day=datetime.fromisoformat(daily['t'].replace('Z','+00:00'))
                prior=datetime.fromisoformat(previous['t'].replace('Z','+00:00'))
                evidence[symbol]['observed_at'] = at.isoformat()
                if (any(t.tzinfo is None for t in (at,day,prior)) or not 0<=(evaluated-at).total_seconds()<900
                        or day.astimezone(NY).date()!=now.astimezone(NY).date()
                        or not timedelta(0)<day-prior<=timedelta(days=5)):
                    evidence[symbol]['snapshot_status'] = 'stale_or_wrong_session'
                    continue
                price,volume,close=map(lambda x:Decimal(str(x)),(trade['p'],daily['v'],previous['c']))
                if not all(v.is_finite() and v>0 for v in (price,volume,close)):continue
                measured = measurements(price, volume, close, previous.get('v'),
                    at=at, prior=(prior_snapshots or {}).get(symbol))
                fresh.add(symbol)
                scores[symbol] = measured['score']
                evidence[symbol] = {'snapshot_status': 'fresh', **measured}
                checkpoint[symbol] = {'observed_at': at.isoformat(), 'price': str(price)}
            except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError):
                continue
    ranked=sorted(fresh,key=lambda s:(-scores[s],s))
    for rank, symbol in enumerate(ranked, 1): evidence[symbol]['snapshot_rank'] = rank
    return {'requested':len(symbols),'received':len(received),'fresh':len(fresh),
            'unavailable_or_stale':len(symbols)-len(fresh),'failed_batches':failures,
            'ranked_symbols':ranked,'feed':'iex','observed_at':now.isoformat(),
            'symbol_evidence':evidence, 'checkpoint':checkpoint,
            'relative_volume_basis':'current_daily_bar_vs_previous_daily_bar_not_same_time'}
