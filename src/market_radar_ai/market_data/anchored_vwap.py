"""Fixed session-open AVWAP experiment. Bar approximation, never a trader's calls."""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import Candle
from .pullback import ema

D = Decimal
NY = ZoneInfo('America/New_York')
STRATEGY = 'session_open_avwap_reclaim_v1'
RULES = {
    'strategy_id': STRATEGY, 'anchor': 'current_regular_session_09:30_America/New_York',
    'bar_price': 'HLC3_volume_weighted_IEX_only', 'minimum_five_minute_bars': 18,
    'fifteen_minute_trend': 'completed_buckets_EMA3_above_rising_EMA6_and_close_above_EMA6',
    'daily_trend': 'previous_completed_close_above_rising_SMA5_using_six_sessions',
    'reclaim': 'previous_close_at_or_below_its_AVWAP_then_bullish_close_above_rising_AVWAP',
    'maximum_avwap_extension_bps': '100', 'minimum_relative_volume_3_vs_prior15': '1.25',
    'minimum_session_notional_usd': '1000000', 'maximum_reference_spread_bps': '20',
    'entry': 'reclaim_bar_high_plus_10bps', 'stop': 'last_three_bar_low_minus_0.1_ATR14',
    'minimum_stop_width': 'max_20bps_or_0.5_ATR14', 'maximum_stop_width_bps': '300',
    'target': 'net_2R_capped_at_observed_prior_session_peak_and_prior_daily_high',
    'maximum_entry_gap_bps': '20', 'entry_lifetime_seconds': 60,
    'maximum_planned_loss_eur': '20', 'paper_allocation_eur': '500',
    'round_trip_cost_bps': '40', 'exit_window_seconds': 30,
    'repeat_policy': 'first_qualifying_setup_per_symbol_per_session',
    'scope': 'captured_US_stocks_only_long_only_shadow_no_AI_no_alerts',
}


def measure(candles, daily, *, symbol, now):
    """Require the real fixed anchor, complete buckets and only prior daily bars.

    No re-anchoring, forward filling or rolling-window fallback. Returns explicit
    blockers even when the pattern does not form, so screening coverage is visible.
    """
    features = {'strategy_id': STRATEGY, 'state': 'UNAVAILABLE'}
    def blocked(reason): return {'features': features, 'blockers': [reason]}
    if now.tzinfo is None: raise ValueError('aware_method_clock_required')
    local = now.astimezone(NY)
    if local.weekday() >= 5 or not (9,30) <= (local.hour,local.minute) < (16,0):
        return blocked('regular_session_not_open_by_clock')
    try:
        rows = [Candle.model_validate(c.model_dump() if isinstance(c,Candle) else c) for c in candles]
        days = [Candle.model_validate(c.model_dump() if isinstance(c,Candle) else c) for c in daily]
        if not 18 <= len(rows) <= 78: return blocked('at_least_90_minutes_required')
        anchor = local.replace(hour=9,minute=30,second=0,microsecond=0)
        if rows[0].timestamp != anchor: return blocked('session_anchor_bar_missing')
        if any(c.timestamp != anchor+timedelta(minutes=5*i) for i,c in enumerate(rows)):
            return blocked('session_bars_have_gaps_or_duplicates')
        if not 300 <= (now-rows[-1].timestamp).total_seconds() < 600:
            return blocked('latest_completed_bar_missing_or_stale')
        for c in rows+days:
            if (c.symbol != symbol or c.source != 'alpaca_iex' or c.quote_currency != 'USD'
                    or not all(x.is_finite() for x in (c.open,c.high,c.low,c.close,c.volume))
                    or min(c.open,c.high,c.low,c.close) <= 0 or c.volume <= 0
                    or c.low > min(c.open,c.close) or c.high < max(c.open,c.close)):
                return blocked('method_bar_identity_or_values_invalid')
        if any(c.interval!='5m' or c.timestamp+timedelta(minutes=5)>now for c in rows):
            return blocked('incomplete_intraday_bar')
        if not 6 <= len(days) <= 10: return blocked('six_prior_daily_bars_required')
        dates = [c.timestamp.astimezone(NY).date() for c in days]
        if (any(c.interval!='1d' for c in days) or dates!=sorted(set(dates))
                or any(d >= local.date() or (local.date()-d).days>21 for d in dates)
                or (local.date()-dates[-1]).days>4):
            return blocked('daily_context_stale_future_or_duplicated')
        # Raw daily prices have no corporate-action adjustment here. Reject large
        # discontinuities rather than interpret a possible split as a trend.
        if any(abs(b.close/a.close-1)>D('.25') for a,b in zip(days,days[1:])):
            return blocked('daily_discontinuity_requires_corporate_action_check')
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):
        return blocked('method_bars_invalid')
    pv = volume = D(0); avwaps=[]
    for c in rows:
        volume += c.volume; pv += (c.high+c.low+c.close)/3*c.volume
        avwaps.append(pv/volume)
    completed = len(rows)//3
    higher_closes = [rows[i*3+2].close for i in range(completed)]
    e3,e6 = ema(higher_closes,3),ema(higher_closes,6)
    sma = sum(c.close for c in days[-5:])/5
    prior_sma = sum(c.close for c in days[-6:-1])/5
    tr = [max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(rows,rows[1:])]
    atr = sum(tr[-14:])/14
    baseline = sum(c.volume for c in rows[-18:-3])/15
    relative = (sum(c.volume for c in rows[-3:])/3)/baseline
    entry = rows[-1].high*D('1.001')
    stop = min(c.low for c in rows[-3:])-atr*D('.1')
    overhead = [max(c.high for c in rows[:-3])]
    if days[-1].high > entry: overhead.append(days[-1].high)
    target_cap = min(overhead)
    features.update(state='MEASURED', anchor_at=rows[0].timestamp.isoformat(),
        last_completed_at=(rows[-1].timestamp+timedelta(minutes=5)).isoformat(),
        avwap=str(avwaps[-1]), previous_avwap=str(avwaps[-2]), last_close=str(rows[-1].close),
        completed_15m_buckets=completed, ema3_15m=str(e3[-1]), ema6_15m=str(e6[-1]),
        daily_sma5=str(sma), prior_daily_sma5=str(prior_sma), daily_last_date=str(dates[-1]),
        atr14=str(atr), relative_volume_3_vs_prior15=str(relative),
        session_notional_usd=str(pv), entry_native=str(entry), stop_native=str(stop),
        target_cap_native=str(target_cap), method_is_our_intraday_adaptation=True)
    blockers=[]
    if not (days[-1].close>sma>prior_sma): blockers.append('daily_trend_not_confirmed')
    if not (e3[-1]>e6[-1]>e6[-2] and higher_closes[-1]>e6[-1]): blockers.append('fifteen_minute_trend_not_confirmed')
    if not (rows[-2].close<=avwaps[-2] and rows[-1].close>avwaps[-1]>avwaps[-2]
            and rows[-1].close>rows[-1].open): blockers.append('fresh_avwap_reclaim_not_formed')
    if (rows[-1].close/avwaps[-1]-1)*10000>D(RULES['maximum_avwap_extension_bps']): blockers.append('extended_above_avwap')
    if relative<D(RULES['minimum_relative_volume_3_vs_prior15']): blockers.append('reclaim_volume_insufficient')
    if pv<D(RULES['minimum_session_notional_usd']): blockers.append('session_liquidity_insufficient')
    if not 0<stop<entry<target_cap: blockers.append('observed_target_room_unavailable')
    if entry-stop<max(entry*D('.002'),atr*D('.5')): blockers.append('stop_too_tight_for_volatility')
    if (entry-stop)/entry*10000>D(RULES['maximum_stop_width_bps']): blockers.append('stop_too_wide')
    return {'features':features,'blockers':blockers}
