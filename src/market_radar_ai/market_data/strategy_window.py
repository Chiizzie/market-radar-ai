"""Explicit paper strategy windows; early stocks never borrow overnight bars."""
from datetime import timedelta
from zoneinfo import ZoneInfo


def profile(rows, *, now):
    if len(rows) >= 20:
        return 'momentum_20_bar_v1'
    if len(rows) < 6 or now.tzinfo is None:
        return None
    local = now.astimezone(ZoneInfo('America/New_York'))
    opening = local.replace(hour=9, minute=30, second=0, microsecond=0)
    if local.weekday() >= 5 or not opening+timedelta(minutes=30) <= now < opening+timedelta(minutes=100):
        return None
    if any(r.source != 'alpaca_iex' or r.interval != '5m'
           or r.timestamp != opening+timedelta(minutes=5*i)
           or r.timestamp+timedelta(minutes=5) > now for i,r in enumerate(rows)):
        return None
    return 'opening_continuation_30m_v1'
