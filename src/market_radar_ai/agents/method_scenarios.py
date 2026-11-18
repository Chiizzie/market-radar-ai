"""Prospective stock-only method scenarios; never approved plans or trader calls."""
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo

from .candidate_packages import digest
from .chart_news import valid_check
from .paper_comparison import aware, _plan
from ..market_data.anchored_vwap import RULES, STRATEGY, measure
from ..market_data.stock_checks import evaluate

D = Decimal
PROTOCOL = {'version': 'method-shadow-v1', 'rules': RULES,
    'fill_clock': 'local_receipt_after_durable_enrolment',
    'news': 'fresh_bounded_query_required_headline_meaning_not_assessed',
    'eligibility': 'unique_US_Invest_catalogue_candidate_not_account_permission',
    'capacity': 40, 'currency': 'EUR', 'no_ai': True, 'no_alerts': True}
PROTOCOL_ID = digest(PROTOCOL)


def scenario(inputs, *, now, measurement_fn=measure, protocol=PROTOCOL):
    """Recomputed from frozen source inputs on enrolment and every event restore."""
    now = aware(now)
    symbol = inputs['symbol']
    protocol_id=digest(protocol)
    measurement = measurement_fn(inputs['candles'], inputs['daily'], symbol=symbol, now=now)
    blockers = list(measurement['blockers'])
    context = inputs['context']
    if (context['symbol'] != symbol or context['provider'] != 'alpaca_iex'
            or context['native_currency'] != 'USD' or context['trade_authorized'] is not False
            or context['schema_version'] != 'stock-context-capture-v1'
            or context['status'] not in ('received','partial')
            or context['daily']['status'] != 'received'
            or context['daily']['bars'] != inputs['daily']
            or not 0 <= (now-aware(context['retrieved_at'])).total_seconds() <= 900
            or not 0 <= (now-aware(inputs['bars_received_at'])).total_seconds() <= 60):
        blockers.append('method_source_context_invalid_or_stale')
    if not valid_check(inputs['news_check'], symbol=symbol, now=now):
        blockers.append('bounded_news_query_missing_or_stale')
    checks = evaluate(inputs['reference_checks'], now=now)
    refs = [r for r in checks['stocks'] if r['symbol'] == symbol]
    ref = refs[0] if len(refs) == 1 else {}
    if checks['market_clock']['status'] != 'open': blockers.append('regular_session_not_confirmed')
    if checks['fx_status'] != 'current_indicative': blockers.append('fresh_fx_unavailable')
    if ref.get('catalogue_status') != 'single_candidate_unverified': blockers.append('unique_invest_catalogue_candidate_missing')
    if ref.get('quote_status') != 'current_reference_only': blockers.append('current_reference_quote_missing')
    result = {'schema_version':'method-shadow-scenario-v1', 'protocol_id':protocol_id,
        'strategy_id':protocol['rules']['strategy_id'], 'candidate_id':'stocks:'+symbol,
        'setup_id':digest({'protocol':protocol_id,'symbol':symbol,'day':now.date().isoformat()}),
        'assembled_at':now.isoformat(), 'shadow_only':True, 'trade_authorized':False,
        'model_calls':0, 'features':measurement['features'], 'blockers':blockers, 'plan':None}
    if blockers: return result
    f = measurement['features']
    entry, stop, cap = map(D, (f['entry_native'],f['stop_native'],f['target_cap_native']))
    bid, ask = D(ref['bid']), D(ref['ask'])
    if D(ref['spread_bps']) > 20: blockers.append('reference_spread_exceeds_20bps')
    if ask >= entry: blockers.append('trigger_already_passed')
    if bid <= stop: blockers.append('setup_already_invalidated')
    rate = D(ref['indicative_ask_eur']) / ask
    entry, stop, cap = (v*rate for v in (entry,stop,cap))
    # Cost-inclusive 2R: (target-entry-cost_per_unit)/(entry-stop+cost_per_unit).
    cost_unit = entry*D('.004')
    target = entry + 2*(entry-stop+cost_unit)+cost_unit
    if target > cap: blockers.append('observed_resistance_prevents_net_2R')
    quantity = min(D(500)/entry,D(20)/(entry-stop+cost_unit)).quantize(D('.000001'),rounding=ROUND_DOWN)
    if quantity <= 0: blockers.append('quantity_unavailable')
    local = now.astimezone(ZoneInfo('Europe/Dublin'))
    exit_by = min(aware(checks['market_clock']['next_close'])-timedelta(minutes=5),
                  local.replace(hour=22,minute=0,second=0,microsecond=0))
    expires = min(now+timedelta(seconds=60),exit_by-timedelta(seconds=30))
    if local.hour >= 22 or exit_by.date()!=now.date() or expires<=now:
        blockers.append('intraday_entry_window_closed')
    if blockers: return result
    plan = {'symbol':symbol, 'currency':'EUR', 'native_currency':'USD', 'entry_eur':str(entry),
        'stop_eur':str(stop), 'target_eur':str(target), 'quantity':str(quantity),
        'assumed_round_trip_cost_eur':str(cost_unit*quantity), 'eur_per_usd':str(rate),
        'invalidation':'Observed bid at or below stop; no overnight simulation',
        'expires_at':expires.isoformat(), 'exit_by':exit_by.isoformat()}
    if _plan(plan).planned_loss > 20: raise ValueError('method_risk_limit')
    result['plan'] = plan
    return result
