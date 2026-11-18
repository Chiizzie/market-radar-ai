"""Prioritize opening charts for existing paper checks using evidence available at the scan."""
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

from ..agents.candidate_packages import digest
from ..dashboard.evidence import export_evidence
from .providers.alpaca import NY, SYMBOL


POLICY = 'opening-chart-routing-v1'


def phase(now):
    if now.tzinfo is None:
        raise ValueError('aware_opening_clock_required')
    local = now.astimezone(NY)
    if local.weekday() >= 5:
        return None
    minutes = (local - local.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds() / 60
    if -90 <= minutes < 0:
        return 'premarket'
    if 0 <= minutes < 15:
        return 'forming_range'
    if 15 <= minutes < 30:
        return 'opening_range'
    if 30 <= minutes < 100:
        return 'opening_continuation'
    return None


def recent_news(feed, now):
    """Use the same publication and retrieval windows as stock qualification."""
    evidence = export_evidence(feed, now=now)
    if evidence['status'] not in ('ok', 'partial'):
        return {}
    latest = {}
    for item in evidence['items']:
        retrieved = datetime.fromisoformat(item['retrieved_at'])
        if item['kind'] != 'news' or not item['intraday_recent'] or not 0 <= (now - retrieved).total_seconds() < 900:
            continue
        stamp = datetime.fromisoformat(item['published_at'])
        for symbol in item['symbols']:
            if SYMBOL.fullmatch(symbol) and (symbol not in latest or stamp > latest[symbol]):
                latest[symbol] = stamp
    return latest


def prior_news(path, now):
    """The previous capture is only a routing hint. Qualification checks a fresh feed."""
    from ..dashboard.scheduled_collection import MAX_CACHE_BYTES, TTL_SECONDS
    try:
        path = Path(path)
        if path.stat().st_size > MAX_CACHE_BYTES:
            return {}
        envelope = json.loads(path.read_bytes())
        payload = envelope['payload']
        if payload['version'] != 1 or digest(payload) != envelope['sha256']:
            return {}
        started = datetime.fromisoformat(payload['collection_started_at'])
        if not 0 <= (now - started).total_seconds() < TTL_SECONDS:
            return {}
        return recent_news(payload['news'], now)
    except (OSError, KeyError, ValueError, TypeError, ArithmeticError, AttributeError):
        return {}


def chart_priority(result, symbol, window, ordinary_priority):
    """A preference for detail slots. All downstream quote, risk and review gates apply."""
    from ..agents.early_opening import PROTOCOL, measure
    from .strategy_window import profile
    bars = result.candles
    now = result.retrieved_at
    if window != phase(now) or not bars or result.provider != 'alpaca_iex' or result.status != 'ok':
        return None
    if window == 'opening_range':
        reading = measure(bars, (), symbol=symbol, now=now)
        if reading['blockers']:
            return None
        prices = reading['features']
        entry, stop, cap = (Decimal(prices[k]) for k in ('entry_native', 'stop_native', 'target_cap_native'))
        cost = entry * Decimal(PROTOCOL['assumed_round_trip_bps']) / 10_000
        if not stop < bars[-1].close < entry or entry + 2 * (entry - stop + cost) + cost > cap:
            return None
        return Decimal(prices['observed_turnover_usd'])
    if window != 'opening_continuation' or not ordinary_priority[0]:
        return None
    if profile(bars, now=now) != 'opening_continuation_30m_v1':
        return None
    if any(b.symbol != symbol or b.quote_currency != 'USD' for b in bars):
        return None
    if not timedelta(minutes=5) <= now - bars[-1].timestamp < timedelta(minutes=10):
        return None
    entry = max(b.high for b in bars[-6:-1]) * Decimal('1.001')
    if not min(b.low for b in bars[-3:]) < bars[-1].close < entry:
        return None
    return Decimal(str(ordinary_priority[1]))
