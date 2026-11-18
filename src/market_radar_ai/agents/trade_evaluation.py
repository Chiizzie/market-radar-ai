"""Offline daily evidence review. No provider, model, alert or order calls."""
import argparse
from .event_archive import EventArchive
import gzip
import json
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from .candidate_packages import digest
from .comparison_live import LiveComparison
from .execution_research import SOURCE_PROTOCOL_ID, SOURCE_PROTOCOL
from .paper_comparison import aware
from .research_views import comparison_rows, exposure

D = Decimal
SHADOW_PROTOCOL = {
    'version': 'observed-stall-exit-15m-v1',
    'entry': 'unchanged_observed_baseline_fill',
    'original_stop_and_target': 'retained',
    'evaluate_after_seconds': 900,
    'exit_observation_window_seconds': 30,
    'required_observed_progress_r': '0.5',
    'maximum_observation_gap_seconds': 15,
    'quote_max_age_seconds': 60,
    'evaluation_quote_observed_at_or_after_deadline': True,
    'costs': 'same_original_flat_round_trip_assumption',
    'application': 'retrospective_diagnostic_only_not_active',
}


def number(value):
    n = D(str(value))
    if not n.is_finite(): raise ValueError('finite_evaluation_number_required')
    return n


def amount(value):
    return format(value, 'f')


def _arm_summary(rows, arm):
    closed = [r for r in rows if r['arms'][arm]['state'] == 'closed']
    states = Counter(r['arms'][arm]['state'] for r in rows)
    reasons = Counter((r['arms'][arm].get('outcome') or {}).get('reason', r['arms'][arm]['state']) for r in rows)
    net = sum((number(r['arms'][arm]['outcome']['net_pnl_eur']) for r in closed), D(0))
    cost = sum((number(r['arms'][arm]['plan']['assumed_round_trip_cost_eur']) for r in closed), D(0))
    fills = [r for r in rows if (r['arms'][arm].get('outcome') or {}).get('entry_at')]
    chase = [(number(r['arms'][arm]['outcome']['entry_fill']) /
              number(r['arms'][arm]['plan']['entry_eur'])-1)*10000 for r in fills]
    waits = [(aware(r['arms'][arm]['outcome']['entry_at']) -
              aware(r['enrolled_at'] if arm == 'code_only' else r['decision_at'])).total_seconds() for r in fills]
    return {'states': dict(sorted(states.items())), 'outcome_reasons': dict(sorted(reasons.items())),
        'closed': len(closed), 'wins': sum(number(r['arms'][arm]['outcome']['net_pnl_eur']) > 0 for r in closed),
        'losses': sum(number(r['arms'][arm]['outcome']['net_pnl_eur']) < 0 for r in closed),
        'closed_net_eur': amount(net) if closed else None,
        'closed_flat_cost_eur': amount(cost) if closed else None,
        'closed_before_flat_cost_eur': amount(net + cost) if closed else None,
        'distinct_closed_symbols': len({r['candidate_id'] for r in closed}),
        'entry_quality': {'observed_fills': len(fills),
            'median_seconds_to_observed_fill': median(waits) if waits else None,
            'median_fill_above_trigger_bps': amount(median(chase)) if chase else None,
            'maximum_fill_above_trigger_bps': amount(max(chase)) if chase else None,
            'note': 'Receipt-time wait from enrolment or AI approval; observed ask versus planned trigger, not broker latency or slippage.'}}


def stall_exit(rows, events, arm):
    """One declared what-if, refusing sparse paths; never claims unseen prices."""
    quotes = defaultdict(dict)
    for event in events:
        if event['kind'] != 'quote': continue
        p = json.loads(event['payload_json']); received = aware(p['received_at'])
        observed = aware(p['quote']['observed_at'])
        if not 0 <= (received - observed).total_seconds() <= SHADOW_PROTOCOL['quote_max_age_seconds']: continue
        quotes[p['candidate_id']][received] = (observed, number(p['quote']['bid']))
    results = []
    for r in rows:
        a = r['arms'][arm]; o = a.get('outcome') or {}; plan = a.get('plan')
        if not plan or not o.get('entry_at'): continue
        row = {'setup_id': r['setup_id'], 'candidate_id': r['candidate_id'], 'state': 'unassessed'}
        results.append(row)
        start = aware(o['entry_at']); due = start + timedelta(seconds=900)
        end = aware(o['exit_at']) if o.get('exit_at') else None
        if end is not None and end <= due:
            row['state'] = 'baseline_exited_before_evaluation'; continue
        window_end = min(due + timedelta(seconds=30), aware(plan['exit_by']))
        path = [(at, observed, bid) for at, (observed, bid) in sorted(quotes[r['candidate_id']].items())
                if start <= observed and start <= at <= window_end and (end is None or at < end)]
        eligible = [(at, bid) for at, observed, bid in path if at >= due and observed >= due]
        if not eligible:
            row['state'] = 'missing_evaluation_quote'; continue
        chosen_at, bid = eligible[0]
        path = [(at, observed, px) for at, observed, px in path if at <= chosen_at]
        received_times = [start] + [at for at, _, _ in path]
        observed_times = sorted({start, chosen_at, *(observed for _, observed, _ in path)})
        gap = max((b-a).total_seconds() for times in (received_times, observed_times)
                  for a,b in zip(times,times[1:]))
        row['maximum_observation_gap_seconds'] = gap
        if gap > SHADOW_PROTOCOL['maximum_observation_gap_seconds']:
            row['state'] = 'observation_gap'; continue
        entry = number(o['entry_fill']); unit_risk = entry - number(plan['stop_eur'])
        if unit_risk <= 0:
            row['state'] = 'invalid_unit_risk'; continue
        progress = max((px-entry)/unit_risk for _, _, px in path)
        row['maximum_observed_progress_r'] = amount(progress)
        if progress >= number(SHADOW_PROTOCOL['required_observed_progress_r']):
            row['state'] = 'progress_threshold_reached'; continue
        # If the stored baseline has not closed, no paired delta is invented.
        shadow_net = (bid-entry)*number(plan['quantity'])-number(plan['assumed_round_trip_cost_eur'])
        baseline_net = number(o['net_pnl_eur']) if o.get('net_pnl_eur') is not None else None
        row.update(state='hypothetical_early_exit', exit_at=chosen_at.isoformat(),
            exit_bid_eur=amount(bid), shadow_net_eur=amount(shadow_net),
            baseline_net_eur=amount(baseline_net) if baseline_net is not None else None,
            paired_delta_eur=amount(shadow_net-baseline_net) if baseline_net is not None else None)
    paired = [r for r in results if r.get('paired_delta_eur') is not None]
    return {'protocol': SHADOW_PROTOCOL, 'protocol_id': digest(SHADOW_PROTOCOL),
        'status': 'retrospective_diagnostic_not_a_strategy_result', 'states': dict(Counter(r['state'] for r in results)),
        'paired_count': len(paired), 'paired_distinct_symbols': len({r['candidate_id'] for r in paired}),
        'paired_delta_eur': amount(sum((number(r['paired_delta_eur']) for r in paired),D(0))) if paired else None,
        'rows': results, 'note': 'Selected after observing this day, so any improvement is hindsight-biased. Sparse paths are excluded, not treated as no progress. The paired subset is coverage-selected and its delta is not a full-cohort or portfolio result. Observed quotes cannot prove an intrapoll high/low. Validate a frozen rule on later unseen sessions before any adoption.'}


def fill_quote_quality(rows, events, arm):
    """Audit the exact fill observations, without changing fills or outcomes."""
    quotes=defaultdict(set)
    for event in events:
        if event['kind']!='quote':continue
        p=json.loads(event['payload_json']);q=p['quote']
        quotes[(p['candidate_id'],aware(p['received_at']))].add((q.get('bid'),q.get('ask')))
    findings=[];checked=0;wide=0;unavailable=0;maximum=None
    for row in rows:
        outcome=row['arms'][arm].get('outcome') or {}
        for side in ('entry','exit'):
            at=outcome.get(side+'_at')
            if not at:continue
            item={'setup_id':row['setup_id'],'candidate_id':row['candidate_id'],'side':side,'fill_at':at}
            observed=quotes.get((row['candidate_id'],aware(at)),set())
            try:
                if len(observed)!=1:raise ValueError('exact_fill_quote_unavailable')
                bid,ask=map(number,next(iter(observed)))
                if not 0<bid<=ask:raise ValueError('invalid_fill_quote')
                spread=(ask-bid)/((ask+bid)/2)*10000
                checked+=1;maximum=spread if maximum is None else max(maximum,spread)
                if spread>20:
                    wide+=1;findings.append({**item,'reason':'reference_spread_exceeds_20bps',
                        'bid_eur':amount(bid),'ask_eur':amount(ask),'spread_bps':amount(spread)})
            except (ValueError,TypeError,ArithmeticError):
                unavailable+=1;findings.append({**item,'reason':'exact_fill_quote_unavailable_or_invalid'})
    return {'threshold_bps':'20','checked_fills':checked,'wide_spread_fills':wide,
        'unavailable_fills':unavailable,'maximum_spread_bps':amount(maximum) if maximum is not None else None,
        'requires_review':bool(wide or unavailable),'findings':findings,'outcomes_changed':False,
        'note':'Exact receipt-time fill observations only; no nearest-price substitution. Wide reference-venue spreads can dominate simulated P/L and do not establish an executable broker fill. Flag gains and losses equally. Original fills, costs and outcomes remain unchanged; a flag alone does not prove a quote was erroneous.'}


def evaluate(events, execution, *, day=None):
    if (execution['schema_version'] != 'execution-research-report-v1'
            or execution['source_protocol_id'] != SOURCE_PROTOCOL_ID
            or execution['dataset_kind'] != 'forward' or execution['trade_authorized'] is not False):
        raise ValueError('current_forward_execution_source_required')
    now = aware(execution['as_of']); day = day or execution['evaluation_day']
    if day > now.date().isoformat(): raise ValueError('future_evaluation_day')
    source_hash = events.source_digest() if isinstance(events, EventArchive) else digest(events)
    if execution['source_sha256'] != source_hash or execution['source_events'] != len(events):
        raise ValueError('execution_source_export_mismatch')
    selected = [e for e in events if e['day'] == day]
    class ReadOnlyEvents:
        def read(self, experiment, requested_day, after):
            if experiment != SOURCE_PROTOCOL_ID or requested_day != day:
                raise ValueError('evaluation_partition_mismatch')
            page = [e for e in selected if e['seq'] > after][:1000]
            return {'events': page, 'next': page[-1]['seq'] if page else after}
    # The original validator reconstructs every event with unchanged clocks and
    # hashes. No append/publish interface is exposed by this offline client.
    with TemporaryDirectory() as scratch:
        projection = LiveComparison(Path(scratch)/'projection',client=ReadOnlyEvents(),day=day,
                                    clock=lambda:now,protocol=SOURCE_PROTOCOL)
        projection.sync(); comparison = projection.store.report(now=now)
    rows = comparison_rows(comparison)
    symbols = Counter(r['candidate_id'] for r in rows)
    strategies = {}
    for strategy in sorted({r['strategy_id'] for r in rows}):
        group = [r for r in rows if r['strategy_id'] == strategy]
        strategies[strategy] = {'setups': len(group), **{a:_arm_summary(group,a) for a in ('code_only','ai_reviewed')}}
    books = [{k:v for k,v in b.items() if k != 'details'} for b in execution['books']]
    return {'schema_version':'trade-evaluation-v1','evaluation_day':day,'as_of':now.isoformat(),
        'dataset_kind':'historical_analysis','source_protocol_id':SOURCE_PROTOCOL_ID,
        'source_export_sha256':source_hash,'execution_report_sha256':digest(execution),
        'cohort_count':len(rows),'distinct_symbols':len(symbols),
        'duplicate_symbol_setups':{s:n for s,n in sorted(symbols.items()) if n>1},
        'arms':{a:_arm_summary(rows,a) for a in ('code_only','ai_reviewed')},'by_strategy':strategies,
        'fill_quote_quality':{a:fill_quote_quality(rows,selected,a) for a in ('code_only','ai_reviewed')},
        'closed_trades':{a:[{'setup_id':r['setup_id'],'candidate_id':r['candidate_id'],
            'strategy_id':r['strategy_id'],'outcome':r['arms'][a]['outcome'],
            'assumed_round_trip_cost_eur':r['arms'][a]['plan']['assumed_round_trip_cost_eur']}
            for r in rows if r['arms'][a]['state']=='closed'] for a in ('code_only','ai_reviewed')},
        'exposure':{a:exposure(rows,a,now=now) for a in ('code_only','ai_reviewed')},
        'ai_costs':comparison['ai_costs'],
        'matched_pair_count':comparison['matched_pair_count'],
        'execution':{'since':execution['since'],'source_cohorts':execution['source_cohorts'],
            'source_last_at':execution['source_last_at'],'report_as_of':execution['as_of'],
            'costs_verified':execution['costs_verified'],'books':books,
            'note':'Alternative fictional EUR1000 portfolios; do not add them. This cumulative execution scope may span more than the selected evaluation day. Assumed USD/EUR routes, slippage and levies are not verified broker costs.'},
        'exit_shadow':{a:stall_exit(rows,selected,a) for a in ('code_only','ai_reviewed')},
        'limitations':['One day cannot establish profitability or AI value.',
            'Independent setups can duplicate symbols and assume more capital than the user has.',
            'Flat costs are assumptions; pre-cost P/L still embeds observed bid/ask spread.',
            'No-fill is not zero-profit execution and missing observations can hide triggers.',
            'No live or paper strategy rule, original decision, alert or outcome was changed.'],
        'model_calls':0,'trade_authorized':False}


def markdown(report):
    def eur(value):return '—' if value is None else f'€{number(value):.2f}'
    lines=[f"# Scanner evidence review — {report['evaluation_day']}",'',
        f"{report['cohort_count']} setups across {report['distinct_symbols']} symbols. Historical evidence analysis only; no strategy change.",'',
        f"Source report as of {report['as_of']}; source protocol `{report['source_protocol_id']}`. Input hashes and complete hypothetical closed-trade rows are retained in the accompanying JSON.",'',
        '| Arm | Closed | Wins / losses | Before flat costs | Flat costs | Net |',
        '|---|---:|---:|---:|---:|---:|']
    for arm,a in report['arms'].items():
        lines.append(f"| {arm} | {a['closed']} | {a['wins']} / {a['losses']} | {eur(a['closed_before_flat_cost_eur'])} | {eur(a['closed_flat_cost_eur'])} | {eur(a['closed_net_eur'])} |")
    lines += ['', f"Trading net excludes separate AI research costs: {eur(report['ai_costs']['settled_estimated_eur'])} recorded estimated cost, with {report['ai_costs']['unreconciled_candidates']} candidates lacking a complete reconciliation (including unreviewed candidates; this does not imply extra spending). This does not establish the complete AI cost or the AI's comparative value."]
    lines += ['', '## Entry and exit evidence','']
    for arm,a in report['arms'].items():lines.append(f"- {arm}: "+', '.join(f'{k}: {v}' for k,v in a['outcome_reasons'].items()))
    lines += ['', '## Reference-quote quality','',
        'Wide reference-venue spreads can dominate simulated results. These are not verified broker fills. Exact quote evidence is checked for both winning and losing entries/exits; no historical result is rescored.','']
    for arm,q in report['fill_quote_quality'].items():
        lines.append(f"- {arm}: {q['checked_fills']} exact fill quotes checked; {q['wide_spread_fills']} above 20bps; {q['unavailable_fills']} unavailable/invalid. Maximum observed spread: "+('unavailable' if q['maximum_spread_bps'] is None else f"{number(q['maximum_spread_bps']):.2f}bps")+'.')
        for item in q['findings']:
            lines.append(f"  - {item['candidate_id']} {item['side']} at {item['fill_at']}: {item['reason']}"+(f" ({number(item['spread_bps']):.2f}bps)." if 'spread_bps' in item else '.'))
    lines += ['', '## Strategy and exposure context','',
        '| Strategy | Setups | Code closed | Code net | AI closed | AI net |','|---|---:|---:|---:|---:|---:|']
    for strategy,s in report['by_strategy'].items():
        lines.append(f"| {strategy} | {s['setups']} | {s['code_only']['closed']} | {eur(s['code_only']['closed_net_eur'])} | {s['ai_reviewed']['closed']} | {eur(s['ai_reviewed']['closed_net_eur'])} |")
    lines += ['', 'Repeated symbol setups: '+', '.join(f'{symbol}: {count}' for symbol,count in report['duplicate_symbol_setups'].items())+'.','']
    for arm,e in report['exposure'].items():
        lines.append(f"- {arm}: peak {e['peak_assumed_concurrent_positions']} simultaneous hypothetical positions, {eur(e['peak_assumed_concurrent_capital_eur'])} assumed capital. These independent setups enforce no account capital limit.")
    for arm,a in report['arms'].items():
        q=a['entry_quality']
        if q['observed_fills']:
            lines.append(f"- {arm}: {q['observed_fills']} observed fills; median wait {q['median_seconds_to_observed_fill']:.1f}s from enrolment/approval, median observed ask above trigger {number(q['median_fill_above_trigger_bps']):.2f} bps. This is not broker execution latency.")
    lines += ['', '## Capital and cost alternatives','',
        '| Profile | Arm | Considered | Closed | Net | Blocks |','|---|---|---:|---:|---:|---|']
    for b in report['execution']['books']:
        lines.append(f"| {b['profile']} | {b['arm']} | {b['considered']} | {b['closed']} | {eur(b['closed_net_pnl_eur'])} | "+', '.join(f'{k}: {v}' for k,v in b['blocked_reasons'].items())+' |')
    lines += ['',report['execution']['note'],'', '## One fixed exit diagnostic','',
        'At 15 minutes after the original observed fill, exit on the first fresh bid within 30 seconds only if sampled progress stayed below +0.5R. The chosen market observation must be at or after the evaluation time. Keep original stop/target, and refuse paths with any source-observation or receipt gap over 15 seconds, including the final source-to-receipt delay. This rule was proposed after seeing the day: it is hindsight-biased and is not activated.','']
    for arm,s in report['exit_shadow'].items():
        lines.append(f"- {arm}: {s['states']}; paired cases {s['paired_count']} across {s['paired_distinct_symbols']} distinct symbols; paired delta {eur(s['paired_delta_eur'])}.")
    lines += ['', 'The paired subset is selected by data coverage. Its delta is not a full-cohort or portfolio result; unavailable paths cannot be filled with assumed prices. Even dense sampled quotes cannot prove that no price crossed a threshold between observations.']
    lines += ['', '## Next evaluation','',
        'Freeze the entry and cost protocol first. Collect later unseen sessions using the same candidates and entries; evaluate the one declared stall exit alongside the unchanged baseline. Preserve unknown paths, deduplicate symbol exposure in the capital book, reconcile broker costs, and report all arms rather than selecting a favourable result. A minimum sample checkpoint is a progress check, not statistical proof.','',
        '## Limits','']+[f'- {x}' for x in report['limitations']]
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--events',type=Path,required=True);p.add_argument('--execution',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--day')
    args=p.parse_args()
    with EventArchive() as events:
        with gzip.open(args.events,'rt') as f:
            for line in f:events.append(json.loads(line))
        report=evaluate(events,json.loads(args.execution.read_text()),day=args.day)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'trade-evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.output/'trade-evaluation.md').write_text(markdown(report))
    print(json.dumps({'state':'offline_trade_evaluation_created','evaluation_day':report['evaluation_day'],
        'cohort_count':report['cohort_count'],'model_calls':0,'trade_authorized':False}))

if __name__=='__main__':main()
