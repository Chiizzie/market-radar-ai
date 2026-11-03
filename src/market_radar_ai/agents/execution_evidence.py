"""Indicative single-venue spread diagnostics, never broker execution evidence."""
from datetime import datetime
from decimal import Decimal


def assess_quote(quote, *, now):
    result = dict(version='execution-evidence-v1', source='alpaca_iex',
        status='unavailable_or_stale', broker_executable=False, costs_verified=False,
        missing_evidence=['broker_executable_quote','broker_fee_and_fx_schedule','slippage_allowance'])
    try:
        at=datetime.fromisoformat(quote['timestamp'].replace('Z','+00:00'))
        if now.tzinfo is None or at.tzinfo is None or not 0 <= (now-at).total_seconds() <= 120:
            return result
        bid,ask=Decimal(quote['bid_usd']),Decimal(quote['ask_usd'])
        if not all(x.is_finite() and x>0 for x in (bid,ask)) or ask<bid:
            return result
        mid=(bid+ask)/2
        result.update(status='fresh_indicative',observed_at=at.isoformat(),
            bid_usd=str(bid),ask_usd=str(ask),spread_usd=str(ask-bid),
            spread_bps=str((ask-bid)/mid*10000),
            note='IEX spread only; not consolidated NBBO, a Trading 212 quote, or total round-trip costs.')
    except (KeyError,TypeError,ValueError,ArithmeticError):
        pass
    return result
