"""Causal, regular-session stock pullback/reclaim measurements for paper research."""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

STRATEGY = 'trend_pullback_reclaim_v1'
D = Decimal
NY = ZoneInfo('America/New_York')


def ema(values, span):
    alpha = D(2)/D(span+1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha*value+(1-alpha)*out[-1])
    return out


def detect_pullback(candles, *, now):
    """A confirmed reclaim is evidence; the buffered entry must still be ahead.

Only the current regular session can form this pattern. No future candles,
overnight joins, forward-filled gaps or projected resistance are accepted.
"""
    if now.tzinfo is None or not candles:
        return None
    local = now.astimezone(NY)
    if local.weekday() >= 5 or not (9, 30) <= (local.hour, local.minute) < (16, 0):
        return None
    rows = [c for c in candles if c.timestamp.astimezone(NY).date() == local.date()
            and (9, 30) <= (c.timestamp.astimezone(NY).hour, c.timestamp.astimezone(NY).minute) < (16, 0)]
    if (len(rows) < 24 or not 300 <= (now-rows[-1].timestamp).total_seconds() < 900
            or any(b.timestamp-a.timestamp != timedelta(minutes=5) for a,b in zip(rows[-24:-1], rows[-23:]))
            or any(c.interval != '5m' or c.timestamp+timedelta(minutes=5) > now
                   or not all(v.is_finite() for v in (c.open,c.high,c.low,c.close,c.volume))
                   or min(c.open,c.high,c.low,c.close) <= 0 or c.volume < 0
                   or c.low > min(c.open,c.close) or c.high < max(c.open,c.close)
                   for c in rows)):
        return None
    e9, e21 = ema([c.close for c in rows], 9), ema([c.close for c in rows], 21)
    impulse, pullback = rows[-12:-3], rows[-3:]
    peak, trough = max(c.high for c in impulse), min(c.low for c in impulse)
    support, reclaim = min(c.low for c in pullback), max(c.high for c in pullback[:-1])
    height, price = peak-trough, rows[-1].close
    if not (e9[-1] > e21[-1] > e21[-4] and impulse[-1].close > impulse[0].close
            and trough+height*D('.5') <= support < peak
            and min(c.low for c in pullback[:-1]) <= e9[-2]*D('1.003')
            and price > e9[-1] and price > reclaim and price > rows[-1].open
            and D('.004') <= height/support <= D('.08')):
        return None
    entry = reclaim*D('1.001')
    # Cap the half-impulse projection at the old impulse peak and any nearer
    # confirmed two-bar swing high in this observed session. No target inflation
    # to satisfy the downstream, cost-inclusive 2R rule.
    overhead = [peak] if peak > entry else []
    history = rows[:-3]
    for i in range(2, len(history)-2):
        window = history[i-2:i+3]
        high = history[i].high
        if (high > entry and high >= max(c.high for c in window)
                and high > min(c.high for c in window[:2])
                and high > min(c.high for c in window[3:])):
            overhead.append(high)
    target = min([support+height*D('.5'), *overhead])
    if not 0 < support < entry < target:
        return None
    return {'strategy_id': STRATEGY, 'pattern_state': 'CONFIRMED',
            'observed_at': (rows[-1].timestamp+timedelta(minutes=5)).isoformat(),
            'reclaim_native': str(reclaim), 'entry_native': str(entry),
            'stop_native': str(support), 'target_cap_native': str(target),
            'impulse_high': str(peak), 'impulse_low': str(trough),
            'ema9': str(e9[-1]), 'ema21': str(e21[-1]),
            'target_basis': 'Half-impulse projection capped at observed session swing highs; projection is not confirmed resistance.'}
