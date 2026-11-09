"""Frozen prospective 15-minute opening-range experiment. No model or order calls."""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from ..market_data.models import Candle
from .candidate_packages import digest
from .paper_comparison import aware
from .method_scenarios import scenario as common_scenario

D=Decimal
STRATEGY='opening_range_15m_shadow_v1'
PROTOCOL={'version':'early-opening-shadow-v1','rules':{
    'strategy_id':STRATEGY,'range_minutes':15,'admit_until_minutes':30,
    'entry_buffer_bps':10,'maximum_range_pct':5,'minimum_observed_turnover_usd':1000000,
    'target':'net_2R_capped_at_projected_three_range_extension'},
    'fill_clock':'local_receipt_after_durable_enrolment','news':'fresh_bounded_query_required_headline_meaning_not_assessed',
    'eligibility':'unique_US_Invest_catalogue_candidate_not_account_permission',
    'assumed_round_trip_bps':40,'maximum_planned_loss_eur':20,'independent_allocation_eur':500,
    'entry_expiry_seconds':60,'maximum_spread_and_entry_gap_bps':20,
    'capacity':40,'currency':'EUR','no_ai':True,'no_alerts':True}
PROTOCOL_ID=digest(PROTOCOL)


def measure(candles,daily,*,symbol,now):
    now=aware(now);local=now.astimezone(ZoneInfo('America/New_York'))
    opening=local.replace(hour=9,minute=30,second=0,microsecond=0)
    blocked=[];features={}
    if local.weekday()>=5 or not opening+timedelta(minutes=15)<=now<opening+timedelta(minutes=30):
        return {'blockers':['outside_15_to_30_minute_experiment_window'],'features':features}
    try:
        rows=[Candle.model_validate(r) for r in candles]
        expected=int((now-opening).total_seconds()//300)
        if len(rows)!=expected or any(r.symbol!=symbol or r.source!='alpaca_iex' or r.quote_currency!='USD' or r.interval!='5m'
            or r.timestamp!=opening+timedelta(minutes=5*i) or r.volume<=0 for i,r in enumerate(rows)):
            raise ValueError('incomplete_or_wrong_session')
        high=max(r.high for r in rows[:3]);low=min(r.low for r in rows[:3]);width=high-low
        vwap=sum((r.high+r.low+r.close)/3*r.volume for r in rows)/sum(r.volume for r in rows)
        turnover=sum(r.close*r.volume for r in rows[:3])
        entry=high*D('1.001')
        if width<=0 or width/low*100>D(5):blocked.append('opening_range_width_invalid')
        if turnover<1000000:blocked.append('opening_turnover_below_one_million_usd')
        if rows[-1].close<=vwap or rows[-1].close<=rows[0].open:blocked.append('opening_direction_not_confirmed')
        # Once the breakout occurred in a completed post-range bar, no late retry.
        if any(r.high>=entry for r in rows[3:]):blocked.append('opening_trigger_already_passed')
        features={'entry_native':str(entry),'stop_native':str(low),'target_cap_native':str(entry+3*width),
            'range_high_native':str(high),'range_low_native':str(low),'observed_turnover_usd':str(turnover),
            'completed_bars':len(rows),'target_cap_basis':'projected_three_range_extension_not_observed_resistance'}
    except (ValueError,TypeError,KeyError,ArithmeticError):blocked.append('early_opening_bars_invalid_or_incomplete')
    return {'blockers':blocked,'features':features}


def scenario(inputs,*,now):
    return common_scenario(inputs,now=now,measurement_fn=measure,protocol=PROTOCOL)
