"""Bounded Alpaca activity/mover discovery; selection is not trade admission."""
from datetime import datetime, timezone
from itertools import zip_longest
import json
import re
import requests

BASE = 'https://data.alpaca.markets/v1beta1/screener/stocks/'
SYMBOL = re.compile(r'[A-Z][A-Z0-9.\-]{0,14}')


def select(groups, now, limit=8):
    # Interleave activity, gainers and losers; reserve half for rotation.
    ranked = list(dict.fromkeys(s for row in zip_longest(*groups) for s in row if s))
    leaders = ranked[:limit//2]
    tail = ranked[limit//2:]
    offset = (int(now.timestamp())//900 * (limit-len(leaders))) % max(1,len(tail))
    rotated = tail[offset:] + tail[:offset]
    chosen = leaders + rotated[:limit-len(leaders)]
    return ranked, chosen


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
        _,ordered=select([pool],now,limit=min(24,len(pool)) or 8)
        candidates=[]
        local=now.astimezone(ZoneInfo('America/New_York'))
        regular=local.weekday()<5 and (9,30)<=(local.hour,local.minute)<(16,0)
        provider=AlpacaIexProvider(env=env)
        for symbol in ordered:
            if len(candidates)>=8:break
            if not regular:
                candidates.append(symbol);continue
            result=provider.fetch_history(symbol)
            checked=capture_result(result,now=datetime.now(timezone.utc))['payload']
            screening['checked']+=1
            if checked['quality_passed_at_capture']:candidates.append(symbol)
            else:screening['rejected'].append(symbol)
        screening['not_checked']=[s for s in pool if s not in candidates and s not in screening['rejected']]
        selected=candidates
        screening['regular_session_quality_screen']=regular

    if not selected: selected=list(fallback)
    return {'schema_version':'stock-discovery-v1','retrieved_at':now.isoformat(),
            'status':'partial' if failures else 'ok','sources':sources,'failures':failures,
            'scope':'provider_activity_and_movers_not_full_exchange_scan',
            'discovered_count':len(ranked),'selected_symbols':selected,
            'deferred_symbols':[s for s in ranked if s not in selected],
            'selection_policy':'interleaved_top_4_plus_15_minute_rotation_4',
            'screening':screening,'fallback_used':not ranked or (screening['enabled'] and not candidates),'broker_eligibility':'unknown', 'trade_authorized':False}
