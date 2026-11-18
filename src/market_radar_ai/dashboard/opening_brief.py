"""Opening preparation and qualification from the completed collection."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..agents.early_screening import screen
from ..market_data.opening_discovery import phase, recent_news
from ..market_data.providers.alpaca import NY, SYMBOL
from ..market_data.stock_checks import evaluate

DUBLIN = ZoneInfo('Europe/Dublin')


def build(document, feed, qualification, discovery, *, now):
    window = phase(now)
    if window is None:
        return None
    opening = now.astimezone(NY).replace(hour=9, minute=30, second=0, microsecond=0)
    brief = {'schema_version': 'opening-session-brief-v1', 'window': window,
             'as_of': now.isoformat(), 'open_dublin': opening.astimezone(DUBLIN).isoformat(),
             'state': 'venue_clock_unconfirmed', 'preparation': [], 'review_ready': [],
             'model_calls': 0, 'trade_authorized': False}
    route = (discovery or {}).get('opening_route')
    if route and route['window'] == window:
        brief['routing'] = route
    record = document.get('stock_reference_checks')
    if not record:
        return brief
    checks = evaluate(record, now=now)
    expected = 'closed' if window == 'premarket' else 'open'
    if checks['market_clock']['status'] != expected:
        return brief
    if window == 'premarket' and datetime.fromisoformat(record['payload']['market_clock']['next_open']) != opening:
        brief['state'] = 'no_regular_open_today'
        return brief
    brief['state'] = 'observed'
    if window == 'forming_range':
        return brief
    refs = {r['symbol']: r for r in checks['stocks'] if r['catalogue_status'] == 'single_candidate_unverified'}
    if window == 'opening_continuation':
        at = datetime.fromisoformat(qualification['evaluated_at'])
        if (qualification['schema_version'] != 'free-qualification-v1' or qualification['trade_authorized'] is not False
                or not 0 <= (now - at).total_seconds() < 60):
            raise ValueError('opening_qualification_stale')
        candidates = [r for r in qualification['candidates'] if r['market'] == 'stocks']
        ready = [r['symbol'] for r in candidates if r['eligible_for_paper_review'] is True and not r['paper_blockers']
                 and now < datetime.fromisoformat(r['conditional_paper_plan']['expires_at'])]
        brief.update(evaluated=len(candidates), qualification_at=at.isoformat(), review_ready=ready,
                     blockers=dict(Counter(reason for r in candidates for reason in set(r['paper_blockers']))))
        if route and route['window'] == window and 'baseline_collection_symbols' in route:
            baseline = set(route['baseline_collection_symbols'])
            brief['ready_outside_baseline_selection'] = sorted(set(ready) & (set(route['routed_collection_symbols']) - baseline))
            brief['baseline_symbols_without_observed_qualification'] = sorted(baseline - {r['symbol'] for r in candidates})
        return brief
    observations = screen(document, now=now)['candidates']
    news = recent_news(feed, now) if window == 'premarket' else {}
    ranked = (sorted(news, key=lambda s: (-news[s].timestamp(), s)) if window == 'premarket' else
              (brief.get('routing') or {}).get('routed_symbols_with_chart_match', []))
    by_symbol = {r['symbol']: r for r in observations}
    for symbol in ranked:
        row = by_symbol.get(symbol)
        if not row or symbol not in refs or not SYMBOL.fullmatch(symbol) or row.get('native_currency') != 'USD':
            continue
        if window == 'premarket' and row['state'] == 'PREMARKET_RESEARCH':
            high = row.get('available_premarket_high_native')
            low = row.get('available_premarket_low_native')
        elif (window == 'opening_range' and row['state'] == 'OPENING_RESEARCH' and row['source'] == 'alpaca_iex'
              and row.get('opening_range_state') == 'INSIDE_RANGE' and refs[symbol]['quote_status'] == 'current_reference_only'):
            high, low = row['opening_range_high_native'], row['opening_range_low_native']
            quote = refs[symbol]
            if (Decimal(quote['spread_bps']) > 20 or Decimal(quote['ask']) >= Decimal(high) * Decimal('1.001')
                    or Decimal(quote['bid']) <= Decimal(low)):
                continue
        else:
            continue
        if not high or not low or not Decimal(high) > Decimal(low) > 0:
            continue
        brief['preparation'].append({'symbol': symbol, 'high_usd': high, 'low_usd': low, 'source': row['source'],
            'last_bar_end': (datetime.fromisoformat(row['observed_at']) + timedelta(minutes=5)).isoformat()})
        if len(brief['preparation']) == 3:
            break
    return brief


def lines(brief, now):
    if not brief or not 0 <= (now - datetime.fromisoformat(brief['as_of'])).total_seconds() < 60 or phase(now) != brief['window']:
        return []
    window = brief['window']
    if brief['state'] == 'no_regular_open_today':
        return ['US market clock shows no regular open today.']
    if brief['state'] != 'observed':
        return ['Opening evidence unavailable for this capture.']
    opening = datetime.fromisoformat(brief['open_dublin'])
    def clock(offset):
        return (opening + timedelta(minutes=offset)).strftime('%H:%M')
    if window == 'opening_continuation':
        return [f"{len(brief['review_ready'])} of {brief['evaluated']} stocks qualified for opening paper review at this check."
                + (' Awaiting final review for ' + ', '.join(brief['review_ready'][:3]) + '.' if brief['review_ready'] else '')]
    if window == 'forming_range':
        return [f'Opening range completes at {clock(15)} Dublin. The first continuation review can qualify from {clock(30)}.']
    title = 'Pre-open paper watchlist' if window == 'premarket' else '15-minute range for paper research'
    out = [title]
    for row in brief['preparation']:
        end = datetime.fromisoformat(row['last_bar_end']).astimezone(DUBLIN).strftime('%H:%M')
        source = '15-minute delayed SIP' if row['source'] == 'alpaca_sip_delayed' else 'IEX'
        out.append(f"{row['symbol']}  observed ${row['low_usd']}–${row['high_usd']} USD ({source}, through {end} Dublin).")
    if not brief['preparation']:
        out.append('No names met the preparation checks in this capture.')
    out.append(f'Opening range from {clock(15)} Dublin. Continuation review from {clock(30)}.')
    return out


def waiting_for_opening_update(brief, now):
    """Use the existing hourly success slot at the upcoming opening checkpoint."""
    if not brief or brief.get('state') != 'observed':
        return False
    if not 0 <= (now - datetime.fromisoformat(brief['as_of'])).total_seconds() < 60:
        return False
    local = now.astimezone(DUBLIN)
    opening = datetime.fromisoformat(brief['open_dublin']).astimezone(DUBLIN)
    return any(local.replace(minute=0, second=0, microsecond=0) == target.replace(minute=0, second=0, microsecond=0)
               and local < target for target in (opening - timedelta(minutes=45), opening + timedelta(minutes=15)))
