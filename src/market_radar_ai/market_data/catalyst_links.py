"""Sourced competitor discovery, never fabricated direct news or trade admission.

V1 intentionally covers only NVIDIA's documented AMD/Intel competition. Every
fresh headline is a research trigger, not a directional event classification.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import re

VERSION = 'competitor-catalyst-discovery-v1'
RELATIONSHIP_SOURCE = 'https://s201.q4cdn.com/141608511/files/doc_financials/2026/ar/2026-Annual-Report-Web.pdf'
ALIASES = {'NVDA': r'\b(?:NVDA|NVIDIA|Jensen Huang)\b', 'AMD': r'\b(?:AMD|Advanced Micro Devices)\b', 'INTC': r'\b(?:INTC|Intel)\b'}

def headline_mentions_source(title, source):
    return isinstance(title,str) and bool(re.search(ALIASES.get(source,r'(?!)'),title,re.IGNORECASE))

RELATIONSHIPS = {'NVDA': ('AMD', 'INTC'), 'AMD': ('NVDA',), 'INTC': ('NVDA',)}


def fetch_seeds(*, env, clock=lambda: datetime.now(timezone.utc)):
    from ..evidence.alpaca_news import fetch_alpaca_news
    def fetch(symbol):
        return symbol, fetch_alpaca_news(symbol, env=env, clock=clock)
    # Three bounded requests, existing provider credentials, no model calls.
    with ThreadPoolExecutor(max_workers=3) as executor:
        return dict(executor.map(fetch, RELATIONSHIPS))


def stamp(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('naive_time')
    return t


def number(value):
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('nonfinite')
    return n


def response(source, target, *, published, now):
    """Compare aligned post-publication observations, not all-day returns.

    Positive relative movement is evidence consistent with rotation, not proof
    of causation, sector-relative strength, entry quality or a profitable trade.
    """
    try:
        rows = (source, target)
        ends = [stamp(r['observed_at']) for r in rows]
        starts = [stamp(r['prior_observation']['observed_at']) for r in rows]
        for r, start, end in zip(rows, starts, ends):
            if r.get('snapshot_status') != 'fresh' or not 0 <= (now-end).total_seconds() <= 180:
                return {'state': 'awaiting_fresh_prices'}
            if not published <= start < end or not 60 <= (end-start).total_seconds() <= 1800:
                return {'state': 'awaiting_post_news_baseline'}
        if abs((starts[0]-starts[1]).total_seconds()) > 60 or abs((ends[0]-ends[1]).total_seconds()) > 60:
            return {'state': 'unaligned_observation_windows'}
        returns = []
        for r in rows:
            previous, current = number(r['prior_observation']['price']), number(r['price'])
            if min(previous, current) <= 0:
                raise ValueError('price')
            returns.append((current/previous-1)*100)
        relative = returns[1]-returns[0]
        liquid = number(target['turnover_usd']) >= 10_000_000
        supported = returns[1] >= Decimal('.25') and relative >= Decimal('.5') and liquid
        return {'state': 'relative_strength_observed' if supported else 'no_supporting_response',
                'source_return_pct': float(returns[0]), 'target_return_pct': float(returns[1]),
                'relative_return_pp': float(relative), 'target_liquidity_met': liquid,
                'window_start': [t.isoformat() for t in starts],
                'window_end': [t.isoformat() for t in ends]}
    except (KeyError, ValueError, TypeError, AttributeError, ArithmeticError):
        return {'state': 'price_evidence_unavailable'}


def discover_links(news, snapshots, pool, *, now):
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    rows = []; seen = set(); rejected = 0
    for source, targets in RELATIONSHIPS.items():
        report = news.get(source, {})
        try:
            received = stamp(report['retrieved_at'])
            if report.get('status') != 'partial' or not 0 <= (now-received).total_seconds() <= 300:
                continue
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        for item in report.get('items', [])[:10]:
            try:
                published = stamp(item['published_at'])
                if not headline_mentions_source(item['title'], source):
                    raise ValueError('publisher_tag_without_headline_subject')
                if source not in item['symbols'] or not 0 <= (now-published).total_seconds() <= 86400:
                    raise ValueError('unrelated_or_expired')
                if published > received or not item['evidence_id'] or not item['url'].startswith('https://'):
                    raise ValueError('invalid_evidence')
                for target in targets:
                    key = (item['url'], source, target)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({'source_symbol': source, 'symbol': target,
                        'relationship': 'competitor', 'relationship_source': RELATIONSHIP_SOURCE,
                        'relationship_scope': 'accelerated_computing_products; exposures_are_not_identical',
                        'evidence_id': item['evidence_id'], 'headline': item['title'],
                        'news_url': item['url'], 'published_at': published.isoformat(),
                        'news_retrieved_at': received.isoformat(),
                        'direction': 'unknown_hypothesis_only', 'direct_target_news': False,
                        'catalogue_member': target in pool,
                        'response': response(snapshots.get(source, {}), snapshots.get(target, {}), published=published, now=now)})
            except (KeyError, ValueError, TypeError, AttributeError):
                rejected += 1
    rows.sort(key=lambda r: (r['response']['state'] != 'relative_strength_observed', -stamp(r['published_at']).timestamp(), r['symbol']))
    return {'schema_version': VERSION, 'as_of': now.isoformat(), 'rows': rows,
        'priority_symbols': list(dict.fromkeys(r['symbol'] for r in rows if r['catalogue_member'])),
        'source_status': {s: news.get(s, {}).get('status', 'unavailable') for s in RELATIONSHIPS},
        'rejected_items': rejected, 'model_calls': 0, 'trade_authorized': False,
        'scope': 'NVDA_AMD_INTC_documented_competition_only',
        'note': 'Research hypotheses, not causal attribution or buy signals. One page of ten publisher-tagged articles per seed; maximum publication age 24h. Missing news or prices is unknown. Existing admission gates remain in force.'}


def routing_report(report, manifest, qualification):
    """Join actual collection routing and admission reasons without hiding vetoes."""
    selected = {r['symbol']: r for r in manifest.get('symbols', [])}
    candidates = {r['candidate_id']: r for r in qualification.get('candidates', [])}
    rows = []
    for r in report.get('rows', []):
        m = selected.get(r['symbol'], {}); q = candidates.get('stocks:'+r['symbol'])
        rows.append({**r, 'detail_selected': m.get('detail_selected'),
            'selection_reason': m.get('selection_reason', 'selection_evidence_unavailable'),
            'qualification_available': q is not None,
            'qualification_blockers': q.get('paper_blockers', []) if q else [],
            'admission_state': 'not_assessed' if q is None else 'blocked' if q.get('paper_blockers') else 'qualified_not_approved'})
    return {**report, 'rows': rows}
