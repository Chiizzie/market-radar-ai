"""Symbol-independent conditional EUR paper scenarios; never execution admission."""
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo
from ..market_data.admission import FxQuote

D = Decimal


def draft(bars, fx, *, now):
    """Validated MarketEvidence in, explicit fictional assumptions out."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    from .combined_input import MarketEvidence
    bars = MarketEvidence.model_validate(bars.model_dump())
    if not 300 <= (now-bars.candles[-1].timestamp).total_seconds() < 900:
        return None
    local = now.astimezone(ZoneInfo('Europe/Dublin'))
    from ..market_data.strategy_window import profile
    if local.weekday() >= 5 or local.hour >= 22 or profile(list(bars.candles), now=now) is None:
        return None
    rows = bars.candles
    if bars.quote_currency == 'EUR':
        rate, fx_source = D(1), 'native_EUR_no_conversion'
        expiry = now + timedelta(seconds=60)
    else:
        quote = FxQuote.model_validate(fx)
        if quote.native_currency != bars.quote_currency or not 0 <= (now-quote.observed_at).total_seconds() < 900:
            raise ValueError('paper_plan_fx_invalid_or_stale')
        rate, fx_source = quote.eur_per_unit, quote.source
        expiry = min(now+timedelta(seconds=60),quote.observed_at+timedelta(seconds=900))
    # A conditional scenario, not a market order or an optimized strategy.
    entry = max(r.high for r in rows[-6:-1]) * D('1.001')
    stop = min(r.low for r in rows[-3:])
    if not 0 < stop < entry or rows[-1].close >= entry:
        return None
    entry_eur, stop_eur = entry*rate, stop*rate
    costs = entry_eur * D('0.004')
    risk = entry_eur-stop_eur+costs
    quantity = min(D(20)/risk,D(500)/(entry_eur+costs)).quantize(D('.000001'),rounding=ROUND_DOWN)
    if quantity <= 0:
        return None
    exit_by = local.replace(hour=22,minute=0,second=0,microsecond=0)
    expiry = min(expiry,exit_by,rows[-1].timestamp+timedelta(seconds=900))
    if expiry <= now:
        return None
    return dict(schema_version='conditional-eur-paper-scenario-v1',symbol=bars.symbol,
                currency='EUR',native_currency=bars.quote_currency,entry_eur=str(entry_eur),
                stop_eur=str(stop_eur),target_eur=str(entry_eur+2*risk+costs),
                quantity=str(quantity),planned_loss_eur=str(risk*quantity),
                assumed_round_trip_cost_eur=str(costs*quantity),paper_capital_eur='500',
                assumed_round_trip_cost_bps='40',entry_buffer_bps='10',
                fx_rate=str(rate),fx_source=fx_source,expires_at=expiry.isoformat(),
                exit_by=exit_by.isoformat(),trade_authorized=False,
                assumptions='Fictional EUR 500 allocation and assumed 40 bps round-trip costs. Not account funds or verified fees. Tick and quantity increments are unverified.',
                trigger='Conditional break above prior five-bar high plus 10 bps; never enter after expiry.',
                invalidation='Cancel if stop breaks before entry or any evidence expires. Exchange-session exit still needs verification.',
                loss_note='EUR 20 is planned loss under fixed stop fill and FX assumptions; gaps and slippage can increase actual loss.')
