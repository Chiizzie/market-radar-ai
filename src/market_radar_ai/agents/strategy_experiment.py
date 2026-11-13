"""Frozen prospective volume/risk/cost experiment; never an approved trade."""
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import re
from zoneinfo import ZoneInfo

from .candidate_packages import digest
from .chart_news import valid_check
from .paper_comparison import aware
from ..market_data.models import Candle
from ..market_data.stock_checks import evaluate

D = Decimal
NY = ZoneInfo('America/New_York')
VARIANTS = {
    f'{volume}_{risk}_{cost}': {'volume': volume, 'risk': risk, 'cost': cost}
    for volume in ('rolling', 'same_time')
    for risk in ('structural', 'atr')
    for cost in ('flat40', 'usd')
}
VARIANTS.update({f'same_time_atr_{cost}': {'volume': 'same_time', 'risk': 'atr', 'cost': cost}
                 for cost in ('eur', 'stress')})
PROTOCOL = {
    'version': 'volume-risk-cost-v1', 'variants': VARIANTS,
    'since': '2026-11-12', 'validation_first_full_session': '2026-11-13',
    'scope': 'captured_US_Invest_stocks_long_only_no_AI_no_alerts_no_orders',
    'universe': 'same_capture_all_selected_stocks_in_capture_order',
    'repeat': 'first_common_eligible_setup_per_symbol_per_NY_session_all_variants_frozen',
    'common': '20_contiguous_completed_5m_bars_positive_momentum_above_rolling_VWAP_bounded_news_check',
    'feed': 'iex_partial_venue', 'volume_minimum': '1',
    'rolling_volume': 'last5_mean_over_prior15_mean',
    'same_time_volume': 'last5_sum_over_mean_same_NY_buckets_prior10_full_sessions_min5_complete',
    'history_adjustment': 'split', 'history_missing': 'unknown_never_zero_no_fallback',
    'entry': 'previous5_bar_high_plus10bps', 'entry_lifetime_seconds': 180,
    'structural_stop': 'last3_bar_low',
    'structural_target': '2R_net_at_maximum_allowed_entry_gap_including_costs',
    'atr': 'simple_mean_last14_true_ranges_completed_5m',
    'atr_stop': 'min_structural_stop_or_entry_minus1.5ATR14',
    'atr_target': 'min_3R_gross_or6ATR14_or_nearest_observed_prior_bar_resistance_above_entry',
    'maximum_stop_width_bps': '300', 'minimum_net_rr': '2',
    'maximum_reference_spread_bps': '20', 'maximum_entry_gap_bps': '20',
    'quote_policy': 'wide_quotes_cannot_fill_or_invalidate_entry_ambiguous_exit_unresolved',
    'maximum_planned_loss_eur': '20', 'allocation_eur': '500',
    'allocation': 'independent_not_portfolio_alternative_variants_do_not_add',
    'observer_capacity_symbols': 40, 'poll_seconds': 5,
    'exit': 'first_eligible_observed_stop_target_or_last30s_before_session_close_minus5min_or22Dublin',
    'fill_clock': 'max_local_receipt_database_receipt_not_exchange_backdating',
    'costs': {
        'flat40': {'fx_bps': '0', 'slippage_bps': '0', 'flat_bps': '40'},
        'usd': {'fx_bps': '0', 'slippage_bps': '5', 'flat_bps': '0'},
        'eur': {'fx_bps': '15', 'slippage_bps': '5', 'flat_bps': '0'},
        'stress': {'fx_bps': '15', 'slippage_bps': '20', 'flat_bps': '0'},
    },
    'fee_checked': '2026-11-12', 'fee_expires': '2026-12-12',
    'sec_sell_rate': '0.0000206', 'finra_usd_per_share': '0.000195',
    'fee_sources': [
        'https://www.trading212.com/terms/invest',
        'https://helpcentre.trading212.com/hc/en-us/articles/360007081637-What-are-the-applicable-stock-exchange-fees',
        'https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account'],
    'cost_limitations': 'assumed_slippage_and_conditional_sale_levies_not_verified_broker_fees_ADR_taxes_unknown',
    'spread_accounting': 'buy_at_ask_sell_at_bid_do_not_subtract_spread_again',
    'fx': 'source_indicative_EUR_per_USD_held_fixed_not_currency_hedging',
    'no_parameter_tuning_during_validation': True,
}
PROTOCOL_ID = digest(PROTOCOL)


def num(value):
    if isinstance(value, bool): raise ValueError('boolean_not_amount')
    n = D(str(value))
    if not n.is_finite() or abs(n) > D('1e12'): raise ValueError('invalid_amount')
    return n


def text(n):
    return format(n, 'f')


def fees(cost, entry, exit_price, quantity, fx):
    profile = PROTOCOL['costs'][cost]
    if cost == 'flat40': return {'flat_cost_eur': entry * quantity * D('.004')}
    rate = D(profile['fx_bps']) / 10000
    rounded = lambda x: x.quantize(D('.01'), rounding=ROUND_UP)
    return {'entry_fx_eur': rounded(entry * quantity * rate),
            'exit_fx_eur': rounded(exit_price * quantity * rate),
            'sale_levies_eur': rounded(exit_price * quantity * D(PROTOCOL['sec_sell_rate'])
                                     + quantity * fx * D(PROTOCOL['finra_usd_per_share']))}


def economics(plan, cost, *, entry=None, quantity=None):
    slip = D(PROTOCOL['costs'][cost]['slippage_bps']) / 10000
    trigger, stop, target, fx = (num(plan[k]) for k in ('entry_eur', 'stop_eur', 'target_eur', 'fx_rate'))
    e = num(entry) if entry is not None else trigger * D('1.002') * (1 + slip)
    q = num(quantity if quantity is not None else plan['quantity'])
    loss = (e - stop * (1-slip)) * q + sum(fees(cost, e, stop*(1-slip), q, fx).values())
    gain = (target*(1-slip) - e) * q - sum(fees(cost, e, target*(1-slip), q, fx).values())
    capital = e*q + sum(fees(cost, e, target*(1-slip), q, fx).values())
    return {'risk': loss, 'reward': gain, 'capital': capital, 'rr': gain/loss if loss>0 else D(0)}


def historical_volume(source, rows, *, now):
    """Exact same 25-minute window; prior dates only, no zero filling."""
    try:
        if source['protocol_id'] != 'market-context-v1' or source['adjustment'] != 'split':
            raise ValueError('history_protocol')
        if not 0 <= (now-aware(source['available_at'])).total_seconds() <= 900:
            raise ValueError('history_availability')
        local = now.astimezone(NY); anchor = local.replace(hour=9, minute=30, second=0, microsecond=0)
        indexes = [int((r.timestamp-anchor).total_seconds()/300) for r in rows[-5:]]
        if indexes != list(range(indexes[0], indexes[0]+5)) or indexes[0] < 0:
            raise ValueError('volume_window')
        samples=[]; dates=[]
        for item in source['sessions']:
            opening=aware(item['open_at']).astimezone(NY);date=opening.date()
            if date >= local.date() or (local.date()-date).days>35: raise ValueError('future_or_stale_history')
            if date.weekday()>4 or (opening.hour,opening.minute,opening.second)!=(9,30,0):raise ValueError('historical_open')
            if not re.fullmatch('[a-f0-9]{64}',item['source_sha256']):raise ValueError('historical_source_identity')
            if aware(item['close_at'])-aware(item['open_at']) != timedelta(hours=6,minutes=30):
                raise ValueError('short_historical_session')
            if item['sha256'] != digest(item['volumes']) or len(item['volumes']) != 78:
                raise ValueError('volume_source_hash')
            dates.append(date)
            window = item['volumes'][indexes[0]:indexes[-1]+1]
            values = [num(v) for v in window if v is not None]
            if any(v<0 for v in values): raise ValueError('negative_volume')
            usable = len(values)==5
            samples.append({'day':date.isoformat(),'volume':text(sum(values,D(0))) if usable else None,
                            'source_sha256':item['source_sha256']})
        if dates != sorted(set(dates)) or len(dates)>10: raise ValueError('history_dates')
        usable = [D(s['volume']) for s in samples if s['volume'] is not None]
        baseline = sum(usable,D(0))/len(usable) if len(usable)>=5 else None
        total = sum(r.volume for r in rows[-5:])
        return {'ratio':text(total/baseline) if baseline and baseline>0 else None,
                'usable_sessions':len(usable),'samples':samples,'window_start':rows[-5].timestamp.isoformat(),
                'window_end':(rows[-1].timestamp+timedelta(minutes=5)).isoformat(),
                'reason':None if baseline and baseline>0 else 'historical_volume_insufficient'}
    except (KeyError,TypeError,ValueError,ArithmeticError,IndexError):
        return {'ratio':None,'usable_sessions':0,'samples':[],'reason':'historical_volume_unavailable'}


def build(inputs, *, now):
    now=aware(now); symbol=inputs['symbol']; local=now.astimezone(NY)
    result={'schema_version':'strategy-experiment-cohort-v1','protocol_id':PROTOCOL_ID,
            'setup_id':digest({'protocol':PROTOCOL_ID,'symbol':symbol,'day':local.date().isoformat()}),
            'candidate_id':'stocks:'+symbol,'symbol':symbol,'assembled_at':now.isoformat(),
            'source_sha256':digest(inputs),'blockers':[],'features':{},'variants':{},
            'trade_authorized':False,'shadow_only':True,'model_calls':0}
    def fail(reason): result['blockers'].append(reason);return result
    try:
        if local.weekday()>4 or not (9,30)<=(local.hour,local.minute)<(16,0):return fail('outside_regular_session')
        if not PROTOCOL['since']<=local.date().isoformat()<PROTOCOL['fee_expires']:return fail('experiment_or_fee_window_closed')
        rows=[Candle.model_validate(r) for r in inputs['candles']][-20:]
        if len(rows)!=20:return fail('twenty_completed_bars_required')
        anchor=local.replace(hour=9,minute=30,second=0,microsecond=0)
        if any(r.symbol!=symbol or r.source!='alpaca_iex' or r.interval!='5m' or r.quote_currency!='USD'
               or r.timestamp<anchor or r.timestamp+timedelta(minutes=5)>now
               or r.low>min(r.open,r.close) or r.high<max(r.open,r.close)
               or any(not v.is_finite() for v in (r.open,r.high,r.low,r.close,r.volume))
               or min(r.open,r.high,r.low,r.close)<=0 or r.volume<0 for r in rows):return fail('invalid_bars')
        if any(b.timestamp-a.timestamp!=timedelta(minutes=5) for a,b in zip(rows,rows[1:])):return fail('incomplete_bar_window')
        if not 300<=(now-rows[-1].timestamp).total_seconds()<630:return fail('latest_completed_bar_unavailable')
        if not 0<=(now-aware(inputs['bars_received_at'])).total_seconds()<=60:return fail('stale_bar_receipt')
        if not valid_check(inputs['news_check'],symbol=symbol,now=now):return fail('news_risk_check_unavailable')
        checks=evaluate(inputs['reference_checks'],now=now)
        ref=next(r for r in checks['stocks'] if r['symbol']==symbol)
        if checks['fx_status']!='current_indicative' or checks['market_clock']['status']!='open':return fail('reference_clock_or_fx_unavailable')
        if ref['catalogue_status']!='single_candidate_unverified' or ref['quote_status']!='current_reference_only':return fail('broker_catalogue_or_reference_unavailable')
        if num(ref['spread_bps'])>20:return fail('reference_spread_over_20bps')
        total=sum(r.volume for r in rows); base=sum(r.volume for r in rows[:-5])/15
        if total<=0 or base<=0:return fail('volume_unavailable')
        vwap=sum((r.high+r.low+r.close)/3*r.volume for r in rows)/total
        if rows[-1].close<=rows[0].close:return fail('nonpositive_momentum')
        if rows[-1].close<=vwap:return fail('below_rolling_vwap')
        entry=max(r.high for r in rows[-6:-1])*D('1.001'); structural=min(r.low for r in rows[-3:])
        bid,ask=num(ref['bid']),num(ref['ask']);fx=num(ref['indicative_ask_eur'])/ask
        if ask>=entry:return fail('trigger_already_passed')
        if bid<=structural:return fail('structural_stop_already_broken')
        tr=[max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(rows,rows[1:])]
        atr=sum(tr[-14:])/14
        if atr<=0:return fail('volatility_unavailable')
        if atr*D('1.5')>=entry:return fail('volatility_exceeds_price')
        historical=historical_volume(inputs.get('historical_volume',{}),rows,now=now)
        rolling=(sum(r.volume for r in rows[-5:])/5)/base
        resistance=min((r.high for r in rows[:-6] if r.high>entry),default=None)
        deadline=min(aware(checks['market_clock']['next_close'])-timedelta(minutes=5),
                     now.astimezone(ZoneInfo('Europe/Dublin')).replace(hour=22,minute=0,second=0,microsecond=0))
        expires=min(now+timedelta(seconds=180),deadline-timedelta(seconds=30),rows[-1].timestamp+timedelta(minutes=15))
        if deadline.date()!=now.date() or expires<=now:return fail('intraday_window_closed')
        result['features']={'rolling_volume':text(rolling),'same_time_volume':historical,'atr14_usd':text(atr),
                            'vwap_usd':text(vwap),'entry_usd':text(entry),'structural_stop_usd':text(structural),
                            'resistance_usd':text(resistance) if resistance is not None else None}
        for name,variant in VARIANTS.items():
            blocks=[]; ratio=historical['ratio'] if variant['volume']=='same_time' else text(rolling)
            if ratio is None:blocks.append('same_time_volume_unavailable')
            elif D(ratio)<1:blocks.append('relative_volume_below_one')
            stop=min(structural,entry-D('1.5')*atr) if variant['risk']=='atr' else structural
            width=entry-stop
            if not 0<stop<entry or width/entry*10000>300:blocks.append('stop_width_outside_bounds')
            target=min(entry+3*width,entry+6*atr,resistance or D('1e12')) if variant['risk']=='atr' else entry+width
            p={'symbol':symbol,'currency':'EUR','native_currency':'USD','entry_eur':text(entry*fx),
               'stop_eur':text(stop*fx),'target_eur':text(target*fx),'fx_rate':text(fx),'quantity':text(D(500)/(entry*fx)),
               'expires_at':expires.isoformat(),'exit_by':deadline.isoformat(),
               'entry_usd':text(entry),'stop_usd':text(stop),'target_usd':text(target),
               'cost_profile':variant['cost'],'trade_authorized':False}
            # Reserve the worst allowed entry gap. Rounded fees are nonlinear;
            # quantities only decrease and risk/capital are recomputed each time.
            for _ in range(16):
                q=num(p['quantity']).quantize(D('.000001'),rounding=ROUND_DOWN);p['quantity']=text(q)
                e=economics(p,variant['cost'])
                if variant['risk']=='structural' and e['reward']<2*e['risk']:
                    target_e=num(p['target_eur'])+(2*e['risk']-e['reward'])/q+D('.000001')
                    p['target_eur']=text(target_e);p['target_usd']=text(target_e/fx);continue
                if e['risk']<=20 and e['capital']<=500:break
                p['quantity']=text(q*min(D(20)/e['risk'],D(500)/e['capital'])*D('.999'))
            e=economics(p,variant['cost'])
            if num(p['quantity'])<=0 or not 0<e['risk']<=20 or e['capital']>500:blocks.append('sizing_unavailable')
            if e['rr']<2-D('.000001'):blocks.append('net_reward_below_2r')
            p.update(planned_loss_eur=text(e['risk']),reserved_capital_eur=text(e['capital']),net_rr=text(e['rr']))
            result['variants'][name]={'blockers':blocks,'plan':p}
        return result
    except (KeyError,TypeError,ValueError,ArithmeticError,StopIteration):return fail('source_invalid_or_unavailable')


def replay(cohort, observations, *, now, bid_confirmation=False):
    """Receipt-bound fills, symmetric quote quality and no fabricated exits."""
    now=aware(now);start=aware(cohort['enrolled_at']);out={}
    for name,v in cohort['variants'].items():
        p=v['plan'];cost=VARIANTS[name]['cost'];entry=num(p['entry_eur']);stop=num(p['stop_eur']);target=num(p['target_eur'])
        quantity=num(p['quantity']);fx=num(p['fx_rate']);slip=D(PROTOCOL['costs'][cost]['slippage_bps'])/10000
        expiry,deadline=aware(p['expires_at']),aware(p['exit_by'])
        r={'state':'blocked' if v['blockers'] else 'watching','reason':','.join(v['blockers']) or 'awaiting_observed_entry',
           'entry_at':None,'exit_at':None,'entry_usd':None,'exit_usd':None,'net_pnl_eur':None,'fee_eur':None,
           'slippage_eur':None,'observations':0,'rejected_wide_quotes':0}
        if start>=expiry and r['state']=='watching':r.update(state='not_filled',reason='durable_enrolment_after_expiry')
        for o in observations:
            if r['state'] not in ('watching','open'):break
            at=max(aware(o['received_at']),aware(o.get('durable_received_at',o['received_at'])))
            quote=o['quote'];exchange=aware(quote['observed_at'])
            if at>now or exchange<start or at<start or not 0<=(at-exchange).total_seconds()<=60:continue
            bid,ask=num(quote['bid']),num(quote['ask'])
            if not 0<bid<=ask:raise ValueError('invalid_strategy_quote')
            if at>deadline:break
            r['observations']+=1;wide=(ask-bid)/((ask+bid)/2)*10000>20
            if r['state']=='watching':
                if at>=expiry:r.update(state='not_filled',reason='entry_expired');break
                if wide:r['rejected_wide_quotes']+=1;continue
                if bid<=stop:r.update(state='not_filled',reason='invalidated_before_entry');break
                if ask<entry:continue
                if ask>entry*D('1.002'):r.update(state='not_filled',reason='entry_gap_exceeded');break
                fill=ask*(1+slip);e=economics(p,cost,entry=fill)
                if e['risk']>num(p['planned_loss_eur']) or e['capital']>num(p['reserved_capital_eur']) or e['rr']<2-D('.000001'):continue
                if bid_confirmation and bid<entry:continue
                r.update(state='open',reason='observed_reference_entry',entry_at=at.isoformat(),entry_usd=text(fill/fx))
                entry_fill=fill;entry_reference=ask;continue
            reason=('scheduled_exit' if at>=deadline-timedelta(seconds=30) else 'stop' if bid<=stop else 'target' if bid>=target else None)
            if wide:
                r['rejected_wide_quotes']+=1
                if reason:r.update(state='unresolved',reason='exit_quote_quality_unresolved')
                continue
            if reason:
                fill=bid*(1-slip);fee=sum(fees(cost,entry_fill,fill,quantity,fx).values())
                r.update(state='closed',reason=reason,exit_at=at.isoformat(),exit_usd=text(fill/fx),
                         net_pnl_eur=text((fill-entry_fill)*quantity-fee),fee_eur=text(fee),
                         slippage_eur=text(((entry_fill-entry_reference)+(bid-fill))*quantity))
        if r['state']=='watching' and now>=expiry:r.update(state='not_filled',reason='no_observed_entry')
        if r['state']=='open' and now>=deadline:r.update(state='unresolved',reason='no_observed_exit_by_deadline')
        out[name]=r
    return out


def summarize(rows):
    states=dict(Counter(r['state'] for r in rows));closed=[r for r in rows if r['state']=='closed']
    pnl=[num(r['net_pnl_eur']) for r in closed];equity=peak=drawdown=D(0)
    exits=defaultdict(Decimal)
    for r in closed:exits[r['exit_at']]+=num(r['net_pnl_eur'])
    for at,value in sorted(exits.items()):equity+=value;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
    return {'states':states,'closed':len(closed),'wins':sum(p>0 for p in pnl),'losses':sum(p<0 for p in pnl),
            'net_pnl_eur':text(sum(pnl,D(0))) if closed else None,
            'closed_drawdown_eur':text(drawdown) if closed else None,
            'fees_eur':text(sum((num(r['fee_eur']) for r in closed),D(0))) if closed else None,
            'slippage_eur':text(sum((num(r['slippage_eur']) for r in closed),D(0))) if closed else None}
