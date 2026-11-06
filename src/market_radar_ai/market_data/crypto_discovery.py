"""Broker-catalogue crypto discovery with exact EUR venue identity checks."""
from datetime import datetime, timezone
from decimal import Decimal
import requests
from .crypto_identities import IDENTITIES, STABLE_ASSETS
from .crypto_checks import catalogue
from .providers.robinhood import RobinhoodEuropeCatalogue
from .reference_quotes import get_json, digest
from .discovery import catalogue_selection
from .limits import CRYPTO_RESEARCH_LIMIT


def discover(*, now, fetch_catalogue=None, session=None, active=(), clock=lambda:datetime.now(timezone.utc)):
    if now.tzinfo is None:raise ValueError('aware_clock_required')
    counts=dict(catalogue_candidates=0,identity_mapped=0,excluded_stable_assets=0,
        candidate_pool=0,quote_checked=0,quote_usable=0,quote_unavailable=0,
        research_selected=0,research_deferred=0,unmapped=0)
    result={'schema_version':'crypto-discovery-v1','retrieved_at':now.isoformat(),
        'status':'unavailable','coverage':counts,'selected_pairs':[],'failures':[],
        'catalogue':None,'trade_authorized':False,'account_permission_verified':False}
    try:
        payload=(fetch_catalogue or RobinhoodEuropeCatalogue().fetch)()
        record={'payload':payload,'payload_sha256':digest(payload)}
        payload=catalogue(record,now=clock())
        result['catalogue']=record
        identities={(r[0],r[1]):p for p,r in IDENTITIES.items()}
        assets=payload['assets']
        mapped=[identities[(a['symbol'],a['name'])] for a in assets if (a['symbol'],a['name']) in identities]
        pool=sorted(p for p in mapped if IDENTITIES[p][0] not in STABLE_ASSETS)
        counts.update(catalogue_candidates=len(assets),identity_mapped=len(mapped),
            excluded_stable_assets=len(mapped)-len(pool),candidate_pool=len(pool),
            unmapped=len(assets)-len(mapped),research_deferred=len(pool))
    except Exception:
        result['failures'].append('broker_catalogue_unavailable')
        return result
    scores={}
    if pool:
        counts['quote_checked']=len(pool)
        try:
            transport=session or requests.Session()
            params={'pair':','.join(pool)}
            def read(path):
                try:return get_json(path,params,transport)
                except requests.RequestException:
                    # One read-only retry for transport failures, never HTTP
                    # denials, malformed payloads or stale fallback data.
                    return get_json(path,params,transport)
            meta=read('AssetPairs')
            tickers=read('Ticker')
            if meta['error'] or tickers['error']:raise ValueError('provider_error')
            for pair in pool:
                try:
                    asset,name,base,wsname,key=IDENTITIES[pair]
                    rows=[(k,r) for k,r in meta['result'].items() if r.get('altname')==pair]
                    if len(rows)!=1 or rows[0][0]!=key:continue
                    row=rows[0][1]
                    if (row['base'],row['quote'],row['wsname'],row['status'])!=(base,'ZEUR',wsname,'online'):continue
                    ticker=tickers['result'][key]
                    bid,ask,volume,opening,last=map(lambda v:Decimal(str(v)),
                        (ticker['b'][0],ticker['a'][0],ticker['v'][1],ticker['o'],ticker['c'][0]))
                    if not all(v.is_finite() and v>0 for v in (bid,ask,volume,opening,last)) or bid>ask:continue
                    scores[pair]=(float(volume*last),float(abs(last/opening-1)))
                except (KeyError,TypeError,ValueError,ArithmeticError,IndexError):
                    continue
        except Exception:
            result['failures'].append('venue_discovery_unavailable')
    # Rank liquid pairs and movers; reserve half of chart capacity for a stable
    # catalogue rotation, including pairs without usable discovery quotes.
    from itertools import zip_longest
    liquid=sorted(scores,key=lambda p:(-scores[p][0],p))
    movers=sorted(scores,key=lambda p:(-scores[p][1],p))
    ranked=list(dict.fromkeys(p for row in zip_longest(liquid,movers) for p in row if p))
    selected=catalogue_selection(ranked,pool,now,limit=CRYPTO_RESEARCH_LIMIT)
    watched=list(dict.fromkeys(active))
    if len(watched)>CRYPTO_RESEARCH_LIMIT or any(p not in IDENTITIES for p in watched):
        raise ValueError('invalid_active_crypto_capacity_or_identity')
    selected=list(dict.fromkeys([*watched,*selected]))[:CRYPTO_RESEARCH_LIMIT]
    selected_in_pool=len(set(selected)&set(pool))
    counts.update(quote_usable=len(scores),quote_unavailable=len(pool)-len(scores),
        research_selected=selected_in_pool,research_deferred=len(pool)-selected_in_pool)
    result.update(status='partial' if result['failures'] or counts['unmapped'] or counts['quote_unavailable'] else 'ok',
        selected_pairs=selected,retrieved_at=clock().isoformat())
    return result
