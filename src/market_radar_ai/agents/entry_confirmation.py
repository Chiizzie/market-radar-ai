"""Separate prospective entry-confirmation experiment; no AI or orders."""
from decimal import Decimal as D
from .candidate_packages import digest, canonical
from .paper_comparison import aware
from .strategy_experiment import PROTOCOL_ID as SOURCE_PROTOCOL, replay, summarize, num, text

VARIANT = 'rolling_structural_usd'
ARMS = ('ask_trigger', 'bid_confirmed')
PROTOCOL = {
    'version': 'entry-confirmation-v1', 'source_protocol_id': SOURCE_PROTOCOL,
    'source_variant': VARIANT, 'commissioning_from': '2026-11-13',
    'validation_first_day': '2026-11-16',
    'arms': {'ask_trigger': 'ask_at_or_above_trigger',
             'bid_confirmed': 'bid_at_or_above_same_trigger'},
    'common_rules': 'unchanged_source_variant_plans_costs_expiry_and_exit_policy',
    'scope': 'captured_US_Invest_long_only_independent_paper_allocations',
    'universe': 'first_common_eligible_capture_per_symbol_day_capacity40',
    'feed': 'iex_partial_venue', 'poll_seconds': 5, 'maximum_active_symbols': 40,
    'observation': 'independent_quotes_until_both_arms_terminal_no_control_censoring',
    'fill_clock': 'max_local_and_database_receipt_no_backdating',
    'paired_coverage_gap_seconds': 15, 'coverage_quotes': 'fresh_at_receipt_with_spread_at_most_20bps',
    'maximum_cohorts_per_day': 500,
    'prices': 'USD', 'accounting': 'EUR', 'model_calls': 0,
    'trade_authorized': False, 'no_parameter_tuning_during_validation': True,
}
PROTOCOL_ID = digest(PROTOCOL)


def common():
    return {'protocol_id': PROTOCOL_ID, 'shadow_only': True, 'model_calls': 0,
            'trade_authorized': False, 'dataset_kind': 'forward'}


def outcomes(cohort, quotes, now):
    selected = {**cohort, 'variants': {VARIANT: cohort['variants'][VARIANT]}}
    return {arm: replay(selected, quotes, now=now, bid_confirmation=arm == 'bid_confirmed')[VARIANT]
            for arm in ARMS}


def receipt(q):
    return max(aware(q['received_at']), aware(q.get('durable_received_at', q['received_at'])))


def entry_quality(cohort, quotes, result):
    if result['entry_at'] is None:
        return None
    at = aware(result['entry_at'])
    found = [q for q in quotes if receipt(q) == at]
    if not found:
        raise ValueError('entry_quote_missing')
    q = found[0]
    p = cohort['variants'][VARIANT]['plan']
    bid, ask = (num(q['native_quote_usd'][k]) for k in ('bid', 'ask'))
    fill, trigger, stop = map(num, (result['entry_usd'], p['entry_usd'], p['stop_usd']))
    risk = fill-stop
    if risk <= 0:
        raise ValueError('entry_risk_invalid')
    return {
        'entry_bid_usd': text(bid), 'entry_ask_usd': text(ask),
        'simulated_fill_usd': text(fill), 'trigger_usd': text(trigger), 'stop_usd': text(stop),
        'spread_bps': text((ask-bid)/((ask+bid)/2)*10000),
        'ask_above_trigger_bps': text((ask/trigger-1)*10000),
        'initial_shortfall_pct_stop_distance': text((fill-bid)/risk*100),
        'bid_confirmed_at_entry': bid >= trigger,
        'quote_age_seconds': (at-aware(q['quote']['observed_at'])).total_seconds(),
        'slippage_bps_assumed': '5',
    }


def coverage(quotes, pair):
    """Sampling gaps are reported independently of simulated close states."""
    entries = [aware(r['entry_at']) for r in pair.values() if r['entry_at']]
    exits = [aware(r['exit_at']) for r in pair.values() if r['exit_at']]
    if not entries or not exits:
        return {'maximum_gap_seconds': None, 'paired_adequate': False}
    start, end = min(entries), max(exits)
    usable = [q for q in quotes if 0 <= (receipt(q)-aware(q['quote']['observed_at'])).total_seconds() <= 60
              and (num(q['quote']['ask'])-num(q['quote']['bid']))/((num(q['quote']['ask'])+num(q['quote']['bid']))/2)*10000 <= 20]
    times = sorted(set([start, end]+[receipt(q) for q in usable if start <= receipt(q) <= end]))
    gap = max(((b-a).total_seconds() for a,b in zip(times,times[1:])), default=0)
    return {'maximum_gap_seconds': gap,
            'paired_adequate': all(r['state']=='closed' for r in pair.values()) and gap <= 15}


def build_report(worker, now):
    now = aware(now)
    by_symbol = {}
    for q in worker.quotes:
        by_symbol.setdefault(q['candidate_id'], []).append(q)
    arm_rows = {arm: [] for arm in ARMS}
    rows = []
    paired_closed = adequate = 0
    delta = D(0)
    for key,c in sorted(worker.cohorts.items()):
        quotes = by_symbol.get(c['candidate_id'], [])
        pair = outcomes(c, quotes, now)
        cov = coverage(quotes, pair)
        if all(r['state']=='closed' for r in pair.values()):
            paired_closed += 1
        if cov['paired_adequate']:
            adequate += 1
            delta += num(pair['bid_confirmed']['net_pnl_eur'])-num(pair['ask_trigger']['net_pnl_eur'])
        arms = {}
        for arm,result in pair.items():
            arm_rows[arm].append(result)
            arms[arm] = {**result, 'entry_quality': entry_quality(c, quotes, result)}
        rows.append({'setup_id': key, 'candidate_id': c['candidate_id'],
                     'plan': c['variants'][VARIANT]['plan'], 'arms': arms, 'coverage': cov})
    result = {
        **common(), 'schema_version': 'entry-confirmation-report-v1',
        'protocol': PROTOCOL, 'source_protocol_id': SOURCE_PROTOCOL,
        'as_of': now.isoformat(), 'evaluation_day': worker.day,
        'phase': 'validation' if worker.day >= PROTOCOL['validation_first_day'] else 'commissioning',
        'cohort_count': len(worker.cohorts),
        'arms': {arm: summarize(values) for arm,values in arm_rows.items()},
        'comparison': {'both_closed': paired_closed, 'adequate_coverage_pairs': adequate,
                       'excluded': len(worker.cohorts)-adequate,
                       'bid_minus_ask_net_eur': text(delta) if adequate else None},
        'rows': rows, 'rows_omitted': 0, 'screen': worker.screen,
        'observation_health': worker.health,
        'source_event_count': len(worker.source), 'source_events_sha256': digest(worker.source),
        'note': 'Separate paper experiment; no AI, alerts or orders. Commissioning is not unseen validation. '
                'Same frozen plans and costs; only bid confirmation differs. Independent allocations are not a portfolio. '
                'IEX quotes and assumed five-basis-point slippage are not broker fills. Spread is included once by ask/bid fills. '
                'Open, unfilled and unresolved outcomes are not zero returns. Paired results require both closes and no sampling gap over 15 seconds; '
                'this subset can be biased. Full arm counts retain all setups. Do not infer improvement from one session.',
    }
    while len(canonical(result).encode()) > 170000 and result['rows']:
        result['rows'].pop()
        result['rows_omitted'] += 1
    if len(canonical(result).encode()) > 170000:
        raise ValueError('entry_report_capacity')
    return result
