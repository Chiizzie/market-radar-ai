"""Bounded activity and catalogue discovery; selection is not trade admission."""
from datetime import datetime, timezone
from itertools import zip_longest
import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from .limits import STOCK_SCREEN_LIMIT, STOCK_RESEARCH_LIMIT

BASE = 'https://data.alpaca.markets/v1beta1/screener/stocks/'
SYMBOL = re.compile(r'[A-Z][A-Z0-9.\-]{0,14}')
# Trading 212 IDs such as AERO1_US_EQ are not exchange symbols. Never remove
# the numeric suffix to guess an issuer; leave these identities unresolved.
PROVIDER_SYMBOL = re.compile(r'[A-Z][A-Z.\-]{0,14}')


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
    from .pullback import detect_pullback
    pattern = detect_pullback(list(result.candles)[-60:], now=result.retrieved_at)
    return (qualified,float(max(Decimal('-10'),min(Decimal('10'),momentum))+min(relative,Decimal('5')))
            + (2 if pattern else 0))


def catalogue_selection(activity, universe, now, *, limit):
    """Reserve half the batch for fresh leaders, rotate every other catalogue name.

    With no fresh activity, the entire batch rotates. Catalogue order is stable
    across runners, so no process-local cursor or stale mover list is required.
    """
    pool = list(dict.fromkeys(universe))
    members = set(pool)
    leaders = list(dict.fromkeys(s for s in activity if s in members))[:limit // 2]
    tail = [s for s in pool if s not in leaders]
    slots = limit - len(leaders)
    offset = (int(now.timestamp()) // 300 * slots) % max(1, len(tail))
    return leaders + (tail[offset:] + tail[:offset])[:slots]


def discover(*, env, now, fallback, session=None, universe_cache_path=None):
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    transport = session or requests.Session()
    groups, sources, failures = [], [], []
    broad = env.get('ENABLE_BROAD_DISCOVERY') == 'true'
    screen_limit = STOCK_SCREEN_LIMIT if broad else 100
    research_limit = STOCK_RESEARCH_LIMIT-1 if broad else 19
    snapshots = None
    manifest = []
    detail_lanes = {}; sector_leaders = []
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
    universe = None
    pool = list(ranked)
    if env.get('SCREEN_DISCOVERY_DATA') == 'true':
        from .discovery_universe import load_universe
        from .providers.alpaca import AlpacaIexProvider
        from .capture import capture_result
        from zoneinfo import ZoneInfo
        # Fetch/reuse the catalogue even when both activity sources are stale.
        universe = load_universe(now=now, cache_path=universe_cache_path)
        failures.extend(universe['failures'])
        pool = universe['symbols']
        provider_unmapped = []
        if broad:
            provider_unmapped = [s for s in pool if not PROVIDER_SYMBOL.fullmatch(s)]
            pool = [s for s in pool if PROVIDER_SYMBOL.fullmatch(s)]
        # Metadata candidates only, never account buy permission. Excludes ETFs/warrants.
        screening={'enabled':True,'catalogue_stock_candidates':len(pool),
                   'checked':0,'rejected':[],'not_checked':[],'account_permission_verified':False}
        # Screen a broad bounded pool before selecting the enrichment batch.
        # No early stop at the first eight usable symbols; rotation reaches the tail.
        if broad and pool:
            from .providers.alpaca_batch import discover_snapshots
            from .discovery_signals import load_checkpoint, save_checkpoint
            from pathlib import Path
            checkpoint_path = Path(universe_cache_path).with_name('discovery-snapshots.json') if universe_cache_path else None
            prior, cache_status = load_checkpoint(checkpoint_path, now=now)
            snapshots = discover_snapshots(pool, env=env, now=now, prior_snapshots=prior)
            snapshots['checkpoint_load'] = cache_status
            snapshots['checkpoint_save'] = save_checkpoint(checkpoint_path, snapshots.get('checkpoint', {}), now=now)
            if snapshots['failed_batches']:
                failures.append('catalogue_snapshot_batches_unavailable')
            ranked = list(dict.fromkeys(s for row in zip_longest(snapshots['ranked_symbols'],ranked) for s in row if s))
        ordered = catalogue_selection(ranked, pool, now, limit=screen_limit)
        if broad:
            from .coverage_lanes import leaders, reserve_screen
            sector_leaders=leaders((snapshots or {}).get("symbol_evidence", {}))
            ordered=reserve_screen(ordered,pool,sector_leaders,screen_limit)
        members = set(pool)
        leader_symbols = set(list(dict.fromkeys(s for s in ranked if s in members))[:screen_limit//2])
        ranked_positions = {s: i+1 for i,s in enumerate(ranked)}
        technical_reasons = {}
        candidates=[]
        local=now.astimezone(ZoneInfo('America/New_York'))
        regular=local.weekday()<5 and (9,30)<=(local.hour,local.minute)<(16,0)
        priority={}
        if regular:
            batch_results = None
            if broad and ordered:
                from .providers.alpaca_batch import fetch_histories
                batch_results = fetch_histories(ordered, env=env)
            def check(symbol):
                try:
                    result=batch_results[symbol] if batch_results is not None else AlpacaIexProvider(env=env).fetch_history(symbol)
                    checked=capture_result(result,now=datetime.now(timezone.utc))['payload']
                    reasons = sorted({i.get('code', 'quality_check_failed') for i in checked.get('quality_issues', [])})
                    return symbol,checked['quality_passed_at_capture'],technical_priority(result),reasons
                except Exception:
                    # A provider failure is an unavailable observation, not a
                    # reason to abort unrelated symbols or expose raw errors.
                    return symbol, False, (False, 0), ['provider_or_validation_unavailable']
            # Independent sessions per worker; four requests in flight at most.
            with ThreadPoolExecutor(max_workers=4) as executor:
                for symbol,usable,score,reasons in executor.map(check,ordered):
                    screening['checked']+=1
                    technical_reasons[symbol] = reasons if usable else (reasons or ['unusable_completed_bars'])
                    if usable:
                        candidates.append(symbol);priority[symbol]=score
                    else:screening['rejected'].append(symbol)
        else:
            # Pre-open selection prepares news/calendars only. No technical
            # observation has occurred, so do not call these symbols usable.
            candidates=[]
        candidates.sort(key=lambda s:priority.get(s,(False,0)),reverse=True)
        if regular:
            if broad:
                from .coverage_lanes import select_details
                selected,detail_lanes=select_details(candidates,sector_leaders,now,research_limit)
            else:
                _,selected=select([candidates],now,limit=research_limit)
        else:
            if broad:
                from .coverage_lanes import select_details
                research_pool=list(dict.fromkeys([s for s in ranked if s in set(pool)]+pool))
                selected,detail_lanes=select_details(research_pool,sector_leaders,now,research_limit)
            else:
                selected=catalogue_selection(ranked,pool,now,limit=research_limit)
        checked_symbols=set(ordered) if regular else set()
        screening['not_checked']=[s for s in pool if s not in checked_symbols]
        screening['usable_count']=len(candidates)
        screening['deferred_after_screen']=[s for s in candidates if s not in selected]
        screening['technical_screen_limit']=screen_limit
        screening['enrichment_limit']=research_limit
        screening['regular_session_quality_screen']=regular
        selected_set, usable_set = set(selected), set(candidates)
        for symbol in pool:
            checked = symbol in checked_symbols
            usable = symbol in usable_set
            manifest.append({'symbol': symbol,
                **((snapshots or {}).get('symbol_evidence', {}).get(symbol, {'snapshot_status': 'not_requested'})),
                'discovery_rank': ranked_positions.get(symbol),
                'screen_lane': ('priority' if symbol in leader_symbols else 'rotation') if checked else 'not_checked',
                'technical_status': 'usable' if usable else 'unavailable' if checked else 'not_checked',
                'technical_reasons': technical_reasons.get(symbol, []),
                'technical_priority_met': priority[symbol][0] if usable else None,
                'technical_score': priority[symbol][1] if usable else None,
                'detail_selected': symbol in selected_set,
                'detail_lane': detail_lanes.get(symbol),
                'selection_reason': ('selected_for_research' if symbol in selected_set else
                    'outside_technical_budget' if not checked and regular else
                    'premarket_rotation_deferred' if not regular else
                    'technical_data_unavailable' if not usable else 'outside_detail_budget')})

    fallback_used = not selected
    if fallback_used: selected=list(dict.fromkeys(fallback))[:research_limit]
    if fallback_used:
        for row in manifest:
            if row['symbol'] in selected:
                row.update(detail_selected=True, selection_reason='fallback_research_selection')
    selected_members = set(selected) & set(pool)
    checked_count = screening.get('checked', 0)
    usable_count = screening.get('usable_count', 0)
    coverage = {'catalogue_candidates':len(universe['symbols']) if universe else 0,
                'fresh_activity_leads':len(set(s for group in groups for s in group)), 'candidate_pool':len(pool),
                'technical_checked':checked_count, 'technical_usable':usable_count,
                'technical_unavailable':len(screening.get('rejected', [])),
                'technical_deferred':len(pool)-checked_count,
                'research_selected':len(selected_members),
                'research_deferred':len(pool)-len(selected_members)}
    if broad:
        coverage['provider_unmapped'] = len(provider_unmapped) if universe else 0
    return {'schema_version':'stock-discovery-v2','retrieved_at':now.isoformat(),
            'status':'partial' if failures else 'ok','sources':sources,'failures':failures,
            'scope':'catalogue_and_fresh_activity_not_full_exchange_scan' if universe else 'provider_activity_and_movers_not_full_exchange_scan',
            'discovered_count':len(ranked),'selected_symbols':selected,
            'deferred_symbols':[s for s in pool if s not in selected],
            'selection_policy':f'liquid_core_sector_movers_technical_and_rotation_v2_screen_{screen_limit}_enrich_{research_limit}' if broad else f'fresh_leaders_and_catalogue_rotation_every_5_minutes_screen_{screen_limit}_enrich_{research_limit}',
            'snapshot_coverage':{k:v for k,v in snapshots.items() if k not in ('ranked_symbols','symbol_evidence','checkpoint')} if snapshots else None,
            'selection_manifest': manifest,
            'universe':universe, 'coverage':coverage,
            'candidate_pool_symbols':pool,
            'screening':screening,'fallback_used':fallback_used,
            'broker_eligibility':'unknown', 'trade_authorized':False}
