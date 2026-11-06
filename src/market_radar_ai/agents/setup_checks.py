"""Deterministic evidence checks for paper candidates; no model or network calls."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from ..market_data.stock_checks import evaluate

D = Decimal


def reference_checks(document, *, symbol, market, now):
    result = {'broker_account_permission': 'UNKNOWN', 'broker_quote': 'UNKNOWN',
              'verified_costs': 'UNKNOWN', 'instrument_halt': 'UNKNOWN',
              'catalogue_candidate': 'UNKNOWN', 'market_session': 'UNKNOWN',
              'reference_quote': 'UNKNOWN', 'fx': 'UNKNOWN', 'exit_deadline': None}
    if market == 'crypto':
        from ..market_data.crypto_checks import assess
        return {**result, **assess(document, symbol=symbol, now=now)}
    if market != 'stocks':
        return result
    try:
        assessed = evaluate(document['stock_reference_checks'], now=now)
        row = next(r for r in assessed['stocks'] if r['symbol'] == symbol)
    except (KeyError, ValueError, TypeError, StopIteration, ArithmeticError):
        return result
    result['catalogue_candidate'] = ('PASS' if row['catalogue_status']=='single_candidate_unverified'
                                     else 'FAIL' if row['catalogue_status'] in ('not_found','ambiguous') else 'UNKNOWN')
    result['reference_quote'] = 'PASS' if row['quote_status']=='current_reference_only' else 'UNKNOWN'
    result['indicative_ask_eur'] = row.get('indicative_ask_eur')
    result['quote_observed_at'] = row.get('observed_at')
    result['fx'] = 'PASS' if assessed['fx_status']=='current_indicative' else 'UNKNOWN'
    clock = assessed['market_clock']
    result['market_session'] = 'PASS' if clock['status']=='open' else 'FAIL' if clock['status']=='closed' else 'UNKNOWN'
    if clock['status']=='open':
        local = now.astimezone(ZoneInfo('Europe/Dublin'))
        deadline = min(datetime.fromisoformat(clock['next_close'])-timedelta(minutes=5),
                       local.replace(hour=22, minute=0, second=0, microsecond=0))
        if deadline.date() == local.date() and deadline > now:
            result['exit_deadline'] = deadline.astimezone(ZoneInfo('Europe/Dublin')).isoformat()
        else:
            result['market_session'] = 'FAIL'
    return result


def technical_checks(bars):
    """Transparent measurements, not a fitted strategy or success probability."""
    rows = bars.candles[-20:]
    from ..market_data.strategy_window import profile
    strategy = profile(list(bars.candles), now=bars.validated_at)
    if strategy is None:
        return {'state': 'INSUFFICIENT_HISTORY'}
    recent_n = 5 if len(rows) >= 20 else 3
    baseline = sum(c.volume for c in rows[:-recent_n])/(len(rows)-recent_n)
    recent = sum(c.volume for c in rows[-recent_n:])/recent_n
    total = sum(c.volume for c in rows)
    if baseline <= 0 or total <= 0:
        return {'state': 'INSUFFICIENT_VOLUME'}
    vwap = sum(((c.high+c.low+c.close)/3)*c.volume for c in rows)/total
    momentum = (rows[-1].close/rows[0].close-1)*100
    trigger = max(c.high for c in rows[-6:-1])*D('1.001')
    stop = min(c.low for c in rows[-3:])
    measured = {'state': 'MEASURED', 'currency': bars.quote_currency,
            'momentum_20_bars_pct': str(momentum), 'relative_volume_5_vs_15': str(recent/baseline),
            'rolling_20_bar_vwap': str(vwap), 'close_above_rolling_vwap': rows[-1].close>vwap,
            'breakout_trigger_native': str(trigger), 'stop_native': str(stop),
            'trigger_state': 'ALREADY_ABOVE_TRIGGER' if rows[-1].close>=trigger else 'WAITING_FOR_TRIGGER',
            'note': 'Rolling 20-bar VWAP, not full-session VWAP. Measurements are not a buy signal.'}
    measured['strategy_id'] = strategy
    if strategy == 'opening_continuation_30m_v1':
        measured['momentum_window_pct'] = measured.pop('momentum_20_bars_pct')
        measured['relative_volume_3_vs_prior'] = measured.pop('relative_volume_5_vs_15')
        measured['opening_session_vwap'] = measured.pop('rolling_20_bar_vwap')
        measured['completed_bars'] = len(rows)
        measured['note'] = 'Experimental opening-session paper setup: at least six contiguous completed bars from the regular open; last three bars versus earlier opening bars. Not backtested or a proven edge.'
    return measured


def validate_paper_plan(plan, *, now, exit_deadline=None):
    """Independently recompute cost-inclusive risk instead of trusting labels."""
    if plan is None:
        return {'state': 'MISSING', 'failures': ['paper_plan_missing']}
    failures = []
    try:
        entry,stop,target,qty,cost,claimed,capital = [D(str(plan[k])) for k in
            ('entry_eur','stop_eur','target_eur','quantity','assumed_round_trip_cost_eur','planned_loss_eur','paper_capital_eur')]
        if not all(v.is_finite() for v in (entry,stop,target,qty,cost,claimed,capital)):
            raise ValueError('non_finite')
        if not 0 < stop < entry < target or qty <= 0 or cost < 0 or capital <= 0:
            raise ValueError('invalid_levels')
        loss = (entry-stop)*qty+cost
        net_reward = (target-entry)*qty-cost
        if loss>20 or loss<=0 or abs(loss-claimed)>D('0.000001'):
            failures.append('risk_limit_or_arithmetic')
        if net_reward < 2*loss-D('0.000001'):
            failures.append('net_reward_below_2r')
        if entry*qty+cost>capital+D('0.000001'):
            failures.append('paper_capital_exceeded')
        expiry,exit_by=[datetime.fromisoformat(plan[k]) for k in ('expires_at','exit_by')]
        local=now.astimezone(ZoneInfo('Europe/Dublin'))
        if expiry.tzinfo is None or exit_by.tzinfo is None:
            raise ValueError('naive_time')
        if not now<expiry<=exit_by or exit_by.astimezone(local.tzinfo).date()!=local.date():
            failures.append('invalid_expiry_or_overnight')
        if local.weekday()>=5 or local.hour>=22 or exit_by>local.replace(hour=22,minute=0,second=0,microsecond=0):
            failures.append('outside_entry_or_exit_window')
        if exit_deadline is not None and exit_by>datetime.fromisoformat(exit_deadline):
            failures.append('exit_after_market_deadline')
        if plan['currency']!='EUR' or plan['trade_authorized'] is not False:
            failures.append('invalid_plan_scope')
        return {'state': 'PASS' if not failures else 'FAIL', 'failures': failures,
                'recomputed_loss_eur': str(loss), 'net_reward_eur': str(net_reward),
                'verified_broker_costs': False}
    except (KeyError,TypeError,ValueError,ArithmeticError):
        return {'state':'FAIL','failures':['malformed_paper_plan']}
