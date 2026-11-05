"""Free premarket/opening observations. No approval, plan, or paid model calls."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from .candidate_packages import digest
from ..market_data.models import Candle

NY = ZoneInfo('America/New_York')


def screen(document, *, now):
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    rows = []
    for record in document.get('stock_context', []):
        symbol = record.get('payload', {}).get('symbol', 'UNKNOWN')
        result = {'symbol': symbol, 'state': 'UNAVAILABLE', 'trade_authorized': False}
        reason = 'context_invalid_or_stale'
        try:
            p = record['payload']
            if digest(p) != record['payload_sha256'] or p['trade_authorized'] is not False:
                raise ValueError('invalid_context')
            retrieved = datetime.fromisoformat(p['retrieved_at'])
            if retrieved.tzinfo is None or not 0 <= (now-retrieved).total_seconds() < 900:
                raise ValueError('stale_context')
            local = now.astimezone(NY)
            opening = local.replace(hour=9, minute=30, second=0, microsecond=0)
            if local.weekday() >= 5:
                result['state'] = 'WEEKEND_CLOSED'
                rows.append(result)
                continue
            bars = [Candle.model_validate(b) for b in p['intraday']['bars']]
            if any(b.symbol != symbol or b.source != p['provider'] or b.interval != '5m'
                   or b.quote_currency != p['native_currency']
                   or b.timestamp + timedelta(minutes=5) > now
                   or b.timestamp.astimezone(NY).date() != local.date()
                   or not all(v.is_finite() for v in (b.open,b.high,b.low,b.close,b.volume))
                   for b in bars):
                raise ValueError('invalid_bars')
            if any(b.timestamp <= a.timestamp for a,b in zip(bars,bars[1:])):
                raise ValueError('unordered_bars')
            reason = 'no_completed_intraday_bars' if not bars else 'intraday_bars_stale'
            if not bars or not 300 <= (now-bars[-1].timestamp).total_seconds() < 900:
                raise ValueError('missing_current_bars')
            prem = [b for b in bars if b.timestamp < opening]
            regular = [b for b in bars if b.timestamp >= opening]
            result.update(state='PREMARKET_RESEARCH' if now < opening else 'OPENING_RESEARCH',
                          native_currency=p['native_currency'], source=p['provider'],
                          observed_at=bars[-1].timestamp.isoformat(),
                          regular_bars_available=len(regular),
                          latest_close_native=str(bars[-1].close),
                          context_sha256=record['payload_sha256'])
            if prem:
                result['available_premarket_high_native'] = str(max(b.high for b in prem))
                result['available_premarket_low_native'] = str(min(b.low for b in prem))
            first = regular[:3]
            if len(first)==3 and all(b.timestamp == opening+timedelta(minutes=5*i) for i,b in enumerate(first)):
                high, low = max(b.high for b in first), min(b.low for b in first)
                result.update(opening_range_high_native=str(high), opening_range_low_native=str(low),
                              opening_range_state='ABOVE_RANGE' if regular[-1].close>high else
                              'BELOW_RANGE' if regular[-1].close<low else 'INSIDE_RANGE')
            else:
                result['opening_range_state']='WAITING_FOR_COMPLETE_FIRST_15_MINUTES'
            total = sum(b.volume for b in regular)
            if total > 0:
                vwap=sum((b.high+b.low+b.close)/Decimal(3)*b.volume for b in regular)/total
                result['available_regular_bar_vwap_native']=str(vwap)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            result = {'symbol': symbol, 'state': 'UNAVAILABLE', 'reason': reason, 'trade_authorized': False}
        rows.append(result)
    return {'schema_version':'early-screening-v1', 'evaluated_at':now.isoformat(),
            'candidates':rows,'model_calls':0,'trade_authorized':False,
            'note':'Research only; native-currency observations from available IEX bars, not full-market or full-session coverage. Exchange calendar, news, EUR risk and final review remain separate checks.'}
