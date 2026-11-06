"""Bounded Alpaca activity/mover discovery; selection is not trade admission."""
from datetime import datetime, timezone
from itertools import zip_longest
import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

BASE = 'https://data.alpaca.markets/v1beta1/screener/stocks/'
SYMBOL = re.compile(r'[A-Z][A-Z0-9.\-]{0,14}')


def select(groups, now, limit=19):
    # Interleave activity, gainers and losers; reserve half for rotation.
    ranked = list(dict.fromkeys(s for row in zip_longest(*groups) for s in row if s))
    leaders = ranked[:limit//2]
    tail = ranked[limit//2:]
    offset = (int(now.timestamp())//300 * (limit-len(leaders))) % max(1,len(tail))
    rotated = tail[offset:] + tail[:offset]
    chosen = leaders + rotated[:limit-len(leaders)]
    return ranked, chosen


def technical_priority(result):
    """Free ordering only; all entry, news and risk gates still run downstream."""
    rows=getattr(result,'candles',[])[-20:]
    if len(rows)<6:return (False,0)
    from .strategy_window import profile
    if profile(rows, now=result.retrieved_at) is None:return (False,0)
    recent_n=5 if len(rows)>=20 else 3
    baseline=sum(r.volume for r in rows[:-recent_n])/(len(rows)-recent_n)
    recent=sum(r.volume for r in rows[-recent_n:])/recent_n
    volume=sum(r.volume for r in rows)
    if baseline<=0 or volume<=0 or rows[0].close<=0:return (False,0)
    momentum=(rows[-1].close/rows[0].close-1)*100
    relative=recent/baseline
    vwap=sum(((r.high+r.low+r.close)/3)*r.volume for r in rows)/volume
    qualified=momentum>0 and relative>=Decimal('1.5') and rows[-1].close>vwap
    return (qualified,float(max(Decimal('-10'),min(Decimal('10'),momentum))+min(relative,Decimal('5'))))


def discover(*, env, now, fallback, session=None):
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    transport = session or requests.Session()
    groups, sources, failures = [], [], []
    key, secret = env.get('ALPACA_API_KEY'), env.get('ALPACA_API_SECRET')
    for endpoint, params, fields in [('most-actives', {'top':100,'by':'volume'}, ['most_actives']),
                                    ('movers', {'top':50}, ['gainers','losers'])]:
        try:
            if not key or not secret: raise ValueError('missing_credentials')
            with transport.get(BASE+endpoint, params=params,
                    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},
                    timeout=(5,10),allow_redirects=False,stream=True) as response:
                if response.status_code != 200: raise ValueError('http_failure')
                body=bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>500000: raise ValueError('oversize')
            data=json.loads(body)
            stamp=data.get('last_updated',data.get('updated_at'))
            observed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            # Prior-session movers must never be presented as current discovery.
            if observed.tzinfo is None or not 0 <= (now-observed).total_seconds() < 900:
                raise ValueError('stale')
            parsed=[]
            for field in fields:
                rows=data[field]
                if not isinstance(rows,list) or len(rows)>params['top']: raise ValueError('rows')
                symbols=[r['symbol'] for r in rows]
                if any(not isinstance(s,str) or not SYMBOL.fullmatch(s) for s in symbols): raise ValueError('symbol')
                parsed.append(symbols)
            groups.extend(parsed)
            sources.append({'source':endpoint,'observed_at':observed.isoformat()})
        except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
            failures.append(endpoint+'_unavailable_or_stale')
    ranked, selected=select(groups, now)
    screening = {'enabled':False}
    if env.get('SCREEN_DISCOVERY_DATA') == 'true' and ranked:
        from .providers.catalogues import Trading212Catalogue
        from .providers.alpaca import AlpacaIexProvider
        from .capture import capture_result
        from zoneinfo import ZoneInfo
        eligible = set()
        try:
            eligible={r.ticker[:-6] for r in Trading212Catalogue().fetch()
                      if r.ticker.endswith('_US_EQ') and r.type=='STOCK' and r.currencyCode=='USD'}
        except Exception:
            failures.append('discovery_catalogue_unavailable')
        pool=[s for s in ranked if s in eligible]
        # Metadata candidates only, never account buy permission. Excludes ETFs/warrants.
        screening={'enabled':True,'catalogue_stock_candidates':len(pool),
                   'checked':0,'rejected':[],'not_checked':[],'account_permission_verified':False}
        # Screen a broad bounded pool before selecting the enrichment batch.
        # No early stop at the first eight usable symbols; rotation reaches the tail.
        _,ordered=select([pool],now,limit=min(100,len(pool)) or 19)
        candidates=[]
        local=now.astimezone(ZoneInfo('America/New_York'))
        regular=local.weekday()<5 and (9,30)<=(local.hour,local.minute)<(16,0)
        priority={}
        if regular:
            def check(symbol):
                result=AlpacaIexProvider(env=env).fetch_history(symbol)
                checked=capture_result(result,now=datetime.now(timezone.utc))['payload']
                return symbol,checked['quality_passed_at_capture'],technical_priority(result)
            # Independent sessions per worker; four requests in flight at most.
            with ThreadPoolExecutor(max_workers=4) as executor:
                for symbol,usable,score in executor.map(check,ordered):
                    screening['checked']+=1
                    if usable:
                        candidates.append(symbol);priority[symbol]=score
                    else:screening['rejected'].append(symbol)
        else:
            candidates=list(ordered)
        candidates.sort(key=lambda s:priority.get(s,(False,0)),reverse=True)
        _,selected=select([candidates],now,limit=19)
        screening['not_checked']=[s for s in pool if s not in ordered]
        screening['usable_count']=len(candidates)
        screening['deferred_after_screen']=[s for s in candidates if s not in selected]
        screening['technical_screen_limit']=100
        screening['enrichment_limit']=19
        screening['regular_session_quality_screen']=regular

    if not selected: selected=list(fallback)
    return {'schema_version':'stock-discovery-v1','retrieved_at':now.isoformat(),
            'status':'partial' if failures else 'ok','sources':sources,'failures':failures,
            'scope':'provider_activity_and_movers_not_full_exchange_scan',
            'discovered_count':len(ranked),'selected_symbols':selected,
            'deferred_symbols':[s for s in ranked if s not in selected],
            'selection_policy':'screen_up_to_100_then_9_leaders_plus_10_rotating_every_5_minutes',
            'screening':screening,'fallback_used':not ranked or (screening['enabled'] and not candidates),'broker_eligibility':'unknown', 'trade_authorized':False}
