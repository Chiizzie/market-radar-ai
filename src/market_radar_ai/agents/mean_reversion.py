"""Predeclared offline long-only intraday mean-reversion hypothesis; no live activation."""
from datetime import timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from .candidate_packages import digest
from .method_scenarios import scenario as common_scenario
from .paper_comparison import aware
from ..market_data.models import Candle

STRATEGY = 'intraday_range_mean_reversion_offline_v1'
RULES = {'strategy_id':STRATEGY, 'status':'offline_only', 'baseline_bars':20, 'signal_bars':2,
    'maximum_efficiency_ratio':'0.25', 'maximum_baseline_range_pct':'4', 'minimum_stretch_z':'1.5',
    'minimum_baseline_turnover_usd':'1000000', 'entry_buffer_bps':'10',
    'stop':'signal_pair_low_minus_0.1_baseline_ATR14', 'minimum_stop_width':'max_20bps_or_0.5_ATR14',
    'maximum_stop_width_bps':'300', 'target_cap':'mean_of_20_pre_signal_closes',
    'minimum_net_reward_risk':'2', 'assumed_round_trip_cost_bps':'40',
    'maximum_planned_loss_eur':'20', 'no_overnight':True}
PROTOCOL = {'version':'offline-mean-reversion-v1','rules':RULES,'no_ai':True,'no_alerts':True,
            'trade_authorized':False,'status':'offline_only'}
PROTOCOL_ID = digest(PROTOCOL)


def measure(candles, daily, *, symbol, now):
    now=aware(now); f={}; blocks=[]
    try:
        rows=[Candle.model_validate(c) for c in candles]
        if not 22<=len(rows)<=78: raise ValueError('history')
        local=now.astimezone(ZoneInfo('America/New_York'))
        opening=local.replace(hour=9,minute=30,second=0,microsecond=0)
        if local.weekday()>=5 or not opening<=now<opening.replace(hour=16): raise ValueError('session')
        rows=rows[-22:]
        for j,c in enumerate(rows):
            if (c.symbol!=symbol or c.source!='alpaca_iex' or c.interval!='5m' or c.quote_currency!='USD'
                    or c.timestamp<opening or c.timestamp+timedelta(minutes=5)>now or c.volume<=0
                    or (j and c.timestamp-rows[j-1].timestamp!=timedelta(minutes=5))):
                raise ValueError('bars')
        if not 300<=(now-rows[-1].timestamp).total_seconds()<600: raise ValueError('freshness')
        baseline, stretch, recovery=rows[:-2],rows[-2],rows[-1]
        closes=[c.close for c in baseline]; mean=sum(closes)/20
        variance=sum((v-mean)**2 for v in closes)/20
        travel=sum(abs(b-a) for a,b in zip(closes,closes[1:]))
        if variance<=0 or travel<=0: raise ValueError('degenerate_range')
        sigma=variance.sqrt(); efficiency=abs(closes[-1]-closes[0])/travel
        ranges=[max(c.high-c.low,abs(c.high-p.close),abs(c.low-p.close)) for p,c in zip(baseline,baseline[1:])]
        atr=sum(ranges[-14:])/14
        width=(max(c.high for c in baseline)-min(c.low for c in baseline))/mean*100
        turnover=sum(c.close*c.volume for c in baseline)
        z=(stretch.close-mean)/sigma
        entry=recovery.high*D('1.001'); stop=min(stretch.low,recovery.low)-atr*D('.1')
        f={'strategy_id':STRATEGY,'baseline_mean_native':str(mean),'baseline_std_native':str(sigma),
            'baseline_efficiency_ratio':str(efficiency),'baseline_range_pct':str(width),
            'baseline_turnover_usd':str(turnover),'stretch_z':str(z),'baseline_atr14':str(atr),
            'entry_native':str(entry),'stop_native':str(stop),'target_cap_native':str(mean),
            'baseline_last_bar_at':baseline[-1].timestamp.isoformat(), 'state':'MEASURED'}
        if efficiency>D('.25') or width>D(4): blocks.append('range_regime_not_confirmed')
        if turnover<D(1000000): blocks.append('mean_reversion_liquidity_insufficient')
        if z>D('-1.5'): blocks.append('mean_reversion_stretch_not_formed')
        if not stretch.close<recovery.close<mean or recovery.close<=recovery.open:
            blocks.append('mean_reversion_bullish_recovery_missing')
        if not 0<stop<entry<mean: blocks.append('mean_reversion_target_room_unavailable')
        if entry-stop<max(entry*D('.002'),atr*D('.5')): blocks.append('stop_too_tight_for_volatility')
        if (entry-stop)/entry*10000>D(300): blocks.append('stop_too_wide')
    except (ValueError,TypeError,KeyError,ArithmeticError):
        blocks.append('mean_reversion_source_invalid_or_incomplete')
    return {'features':f,'blockers':blocks}


def scenario(inputs, *, now):
    return common_scenario(inputs,now=now,measurement_fn=measure,protocol=PROTOCOL)
