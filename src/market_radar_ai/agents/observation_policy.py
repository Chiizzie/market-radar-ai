"""Prospective quote-quality policy; old packets retain their original replay."""
from datetime import date
from decimal import Decimal

GUARDED = 'reference-quote-quality-v2'
EFFECTIVE_DAY = date(2026, 11, 12)
MAXIMUM_SPREAD_BPS = Decimal('20')


def policy_for_day(day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    return GUARDED if day >= EFFECTIVE_DAY else None


def validate_policy(policy):
    if policy not in (None, GUARDED):
        raise ValueError('unsupported_quote_observation_policy')
    return policy


def spread_bps(quote):
    return (quote.ask-quote.bid)/((quote.ask+quote.bid)/2)*10000


def wide(quote):
    return spread_bps(quote) > MAXIMUM_SPREAD_BPS
