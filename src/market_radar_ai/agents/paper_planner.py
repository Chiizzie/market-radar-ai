"""Deterministic conditional EUR paper draft; never a live or approved trade."""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo
from ..market_data.admission import FxQuote
from ..market_data.models import Candle
from ..market_data.quality import validate_candles

D = Decimal


def draft_nvda(candles, catalogue, fx, *, now, paper_capital_eur, round_trip_cost_bps):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Aware clock required')
    capital, bps = D(str(paper_capital_eur)), D(str(round_trip_cost_bps))
    if not capital.is_finite() or capital <= 0 or not bps.is_finite() or bps < 0:
        raise ValueError('Explicit finite capital and cost assumptions required')
    result = dict(version='eur-paper-draft-v2', state='blocked', trade_authorized=False,
                  paper_only=True, model_calls=0, evaluated_at=now.isoformat(), failures=[], plan=None)
    fail=result['failures']
    local=now.astimezone(ZoneInfo('Europe/Dublin'))
    if local.hour >= 22: fail.append('entry_cutoff')
    try:
        observed=datetime.fromisoformat(catalogue['observed_at'])
        if catalogue['state']!='catalogue_received' or not 0 <= (now-observed).total_seconds() <= 600:
            raise ValueError()
        matches=[r for r in catalogue['candidates'] if r['ticker']=='NVDA_US_EQ'
            and r['isin']=='US67066G1040' and r['type']=='STOCK' and r['currencyCode']=='USD'
            and any(e['name']=='NASDAQ' for e in r['exchanges'])]
        if len(matches)!=1: raise ValueError()
    except (KeyError,TypeError,ValueError): fail.append('catalogue_identity_unverified_or_stale')
    try:
        rows=[Candle.model_validate(c.model_dump() if isinstance(c,Candle) else c) for c in candles]
        result['market_evidence'] = dict(candle_count=len(rows), minimum_candles=20,
            sources=sorted({c.source for c in rows}))
        if len(rows)<20: fail.append('insufficient_completed_candles')
        sources={c.source for c in rows}
        if len(sources)!=1 or not sources <= {'yahoo_finance','alpaca_iex'}:
            fail.append('market_source_unsupported_or_mixed')
        if any(c.symbol!='NVDA' or c.quote_currency!='USD' or c.interval!='5m'
            or c.timestamp+timedelta(minutes=5)>now
            or not all(v.is_finite() for v in (c.open,c.high,c.low,c.close,c.volume)) for c in rows):
            raise ValueError()
        if any((b.timestamp-a.timestamp).total_seconds()!=300 for a,b in zip(rows,rows[1:])):
            fail.append('market_candle_spacing_invalid')
        if rows!=sorted(rows,key=lambda c:c.timestamp) or validate_candles(rows,now=now,max_age_seconds=600,expected_interval_seconds=300):
            raise ValueError()
        if any(c.timestamp.astimezone(ZoneInfo('America/New_York')).date()!=now.astimezone(ZoneInfo('America/New_York')).date() for c in rows):
            raise ValueError()
    except (TypeError,ValueError): fail.append('market_evidence_invalid_or_insufficient')
    try:
        fx=FxQuote.model_validate(fx.model_dump() if isinstance(fx,FxQuote) else fx)
        if fx.native_currency!='USD' or not 0 <= (now-fx.observed_at).total_seconds() <= 900: raise ValueError()
    except (TypeError,ValueError): fail.append('fx_invalid_or_stale')
    if fail: return result
    # Conditional breakout above the previous five completed bars; not an entry now.
    entry=max(c.high for c in rows[-6:-1]).quantize(D('.01'),rounding='ROUND_CEILING')+D('.01')
    stop=min(c.low for c in rows[-3:]).quantize(D('.01'),rounding=ROUND_DOWN)
    if stop>=entry or rows[-1].close>=entry:
        fail.append('conditional_breakout_not_available');return result
    rate=fx.eur_per_unit
    eur_entry,eur_stop=entry*rate,stop*rate
    cost_per_share=eur_entry*bps/D(10000)
    risk_per_share=eur_entry-eur_stop+cost_per_share
    qty=min(D(20)/risk_per_share,capital/(eur_entry+cost_per_share)).quantize(D('.000001'),rounding=ROUND_DOWN)
    if qty<=0: fail.append('capital_too_small');return result
    risk=(eur_entry-eur_stop)*qty+cost_per_share*qty
    expiry=min(now+timedelta(minutes=5),local.replace(hour=22,minute=0,second=0,microsecond=0))
    # Conservative US cash-session exit assumption; calendar/holiday evidence still required.
    session_exit=now.astimezone(ZoneInfo('America/New_York')).replace(hour=16,minute=0,second=0,microsecond=0)
    exit_by=min(local.replace(hour=22,minute=0,second=0,microsecond=0),session_exit)
    if now>=exit_by: fail.append('session_exit_reached');return result
    expiry=min(expiry,exit_by)
    result.update(state='conditional_paper_draft', failures=[], blockers=[
        'account_specific_eligibility_not_verified','live_bid_ask_and_costs_not_verified',
        'exchange_calendar_not_verified','independent_catalyst_review_pending',
        'six_agent_plan_review_not_run'], plan=dict(symbol='NVDA',broker_instrument_id='NVDA_US_EQ',
        currency='EUR',native_currency='USD',strategy='conditional_prior_five_bar_breakout',
        entry_eur=str(eur_entry),stop_eur=str(eur_stop),
        target1_eur=str(eur_entry+2*risk_per_share+cost_per_share),
        target2_eur=str(eur_entry+3*risk_per_share+cost_per_share),
        native_entry_usd=str(entry),native_stop_usd=str(stop),quantity=str(qty),
        planned_loss_eur=str(risk),assumed_round_trip_cost_eur=str(cost_per_share*qty),
        assumed_round_trip_cost_bps=str(bps),paper_capital_eur=str(capital),
        target_basis='Projected net two/three R under fixed cost and FX assumptions; not observed resistance.',
        fx_rate=str(rate),fx_source=fx.source,fx_observed_at=fx.observed_at.isoformat(),
        expires_at=expiry.isoformat(),exit_by=exit_by.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
        invalidation='Cancel if stop is breached before entry, evidence expires, or any blocker remains unresolved.',
        loss_note='Planned loss assumes stop-price fill; gaps, slippage and FX movement can increase actual loss.'))
    if rows[0].source=='alpaca_iex':
        result['blockers'].append('iex_limited_market_coverage')
    result['plan']['market_source']=rows[0].source
    result['plan']['market_observed_at']=rows[-1].timestamp.isoformat()
    return result
