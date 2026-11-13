"""Read-only entry tracing and frozen, zero-extra-call reviewer comparison.

Selection is compared on the SAME code-only reference outcome. This is a
counterfactual selection test, not an executable one-reviewer trading record.
The actual post-approval AI outcome and latency are retained separately.
"""
from collections import Counter
from decimal import Decimal
import json
from statistics import median

from .candidate_packages import digest
from .paper_comparison import aware, metrics
from .review_policy import team_approval_allowed

PROMPT = 'paper-compact-evidence-20261113-v2'
PROTOCOL = {
    'version': 'review-selection-comparison-v1', 'prompt_revision': PROMPT,
    'population': 'first_attempted_setup_per_symbol_day_with_this_prompt_revision',
    'arms': ['code_only', 'independent_chief', 'full_team'],
    'outcome': 'same_code_only_reference_outcome_counterfactual_not_executable',
    'chief': 'independent_final_decision_before_peers_approve_only',
    'team': 'existing_versioned_team_approval_policy',
    'missing': 'retain_incomplete_unfilled_open_unresolved_separately',
    'additional_model_calls': 0, 'strategy_input': False,
}
PROTOCOL_ID = digest(PROTOCOL)


def elapsed(start, end):
    return round((aware(end)-aware(start)).total_seconds(), 3) if start and end else None


def build(store, report):
    rows=report['rows']; traces=[]; comparisons=[]; selected=set()
    with store.connection() as db:
        cohorts={k:json.loads(p) for k,p in db.execute('SELECT id,payload FROM comparison_cohort')}
        reviews={k:json.loads(p) for k,p in db.execute('SELECT id,payload FROM comparison_reviews')}
        quotes={}
        for candidate,raw in db.execute('SELECT candidate,payload FROM comparison_quotes ORDER BY at'):
            quotes.setdefault(candidate,[]).append(json.loads(raw))
    for row in sorted(rows,key=lambda r:(r.get('review_started_at') or r['enrolled_at'],r['setup_id'])):
        cohort=cohorts[row['setup_id']];body=cohort['packet']['packet']
        review=reviews.get(row['setup_id']); plan=body['plan']; outcome=row['code_only'].get('outcome') or {}
        entry=outcome.get('entry_at'); start=row.get('review_started_at'); decision=row.get('decision_at')
        available=[q for q in quotes.get(row['candidate_id'],[])
                   if aware(row['enrolled_at'])<=aware(q['received_at'])<=aware(report['as_of'])]
        before_expiry=[q for q in available if aware(q['received_at'])<=aware(plan['expires_at'])]
        spreads=[]; cross_wide=cross_gap=0
        for q in before_expiry:
            bid=Decimal(q['quote']['bid']);ask=Decimal(q['quote']['ask'])
            spread=(ask-bid)/((ask+bid)/2)*10000;spreads.append(spread)
            if ask>=Decimal(plan['entry_eur']):
                cross_wide+=spread>20
                cross_gap+=ask>Decimal(plan['entry_eur'])*Decimal('1.002')
        reason=('not_selected_for_review' if not start else
                'review_not_completed' if not review else
                'entry_observed_before_approval' if entry and decision and aware(entry)<aware(decision) else
                'no_quote_in_original_entry_window' if not before_expiry else
                'trigger_observed_but_quote_outside_entry_rules' if cross_wide or cross_gap else
                'no_observed_entry_trigger' if not entry else 'observed_entry_after_approval')
        traces.append({'setup_id':row['setup_id'],'candidate_id':row['candidate_id'],
            'strategy_id':row['strategy_id'],'prompt_revision':body.get('prompt_revision'),
            'assembled_at':body['assembled_at'],'enrolled_at':row['enrolled_at'],
            'quote_observed_at':body['reference_checks'].get('quote_observed_at'),
            'review_started_at':start,'decision_at':decision,'original_entry_expires_at':plan['expires_at'],
            'assembly_to_enrol_seconds':elapsed(body['assembled_at'],row['enrolled_at']),
            'enrol_to_review_seconds':elapsed(row['enrolled_at'],start),
            'review_to_decision_seconds':elapsed(start,decision),
            'original_entry_window_seconds':elapsed(row['enrolled_at'],plan['expires_at']),
            'first_quote_receipt':available[0]['received_at'] if available else None,
            'quotes_in_original_entry_window':len(before_expiry),
            'median_reference_spread_bps':str(median(spreads)) if spreads else None,
            'wide_trigger_observations':cross_wide,'gapped_trigger_observations':cross_gap,
            'baseline_entry_at':entry,'baseline_state':row['code_only']['state'],
            'actual_ai_state':row['ai_reviewed']['state'],'decision_blockers':row['decision_blockers'],
            'trace_reason':reason})
        # Population is frozen before outcomes: first attempted packet per asset
        # per day. Incomplete attempts remain in it; never substitute a later win.
        if not start or body.get('prompt_revision')!=PROMPT:continue
        unit=(row['candidate_id'],aware(start).date().isoformat())
        if unit in selected:continue
        selected.add(unit)
        reports=review['audit']['reviews'] if review else []
        chief=next((r for r in reports if r['stage']=='final_decision'),None)
        team=(team_approval_allowed((r['verdict'] for r in reports),
                   policy_version=body.get('review_policy_version')) if reports else None)
        execution=review['audit'].get('execution_evidence',[]) if review else []
        lead=next((c for c in execution if c['stage']=='final_decision'),{})
        costs=[c.get('estimated_cost_microeur') for c in execution]
        known=len(costs)==8 and all(type(c) is int and c>=0 for c in costs)
        comparisons.append({'setup_id':row['setup_id'],'candidate_id':row['candidate_id'],
            'strategy_id':row['strategy_id'],'baseline':row['code_only'],
            'selections':{'code_only':True,'independent_chief':chief['verdict']=='APPROVE_PAPER' if chief else None,
                          'full_team':team},
            'actual_ai_state':row['ai_reviewed']['state'],
            'review_to_decision_seconds':elapsed(start,decision),
            'chief_call_seconds':lead.get('elapsed_seconds'),
            'cost_microeur':{'code_only':0,'independent_chief':lead.get('estimated_cost_microeur'),
                             'full_team':sum(costs) if known else None},
            'recorded_team_cost':row.get('ai_cost')})
    arms={}
    for arm in PROTOCOL['arms']:
        admitted=[r['baseline'] for r in comparisons if r['selections'][arm] is True]
        matched=[r for r in comparisons if r['baseline']['state']=='closed' and r['selections'][arm] is not None]
        deltas=[];net=[]
        for r in matched:
            base=Decimal(r['baseline']['outcome']['net_pnl_eur'])
            pnl=base if r['selections'][arm] else Decimal(0)
            deltas.append(pnl-base)
            cost=r['cost_microeur'][arm]
            if type(cost) is int:net.append(pnl-base-Decimal(cost)/1_000_000)
        arms[arm]={'selected_outcomes':metrics(admitted),
            'not_selected':sum(r['selections'][arm] is False for r in comparisons),
            'incomplete':sum(r['selections'][arm] is None for r in comparisons),
            'matched_closed':len(matched),'excluded_from_closed_comparison':len(comparisons)-len(matched),
            'matched_delta_before_model_cost_eur':str(sum(deltas,Decimal(0))) if deltas else None,
            'matched_delta_after_model_cost_eur':str(sum(net,Decimal(0))) if net and len(net)==len(matched) else None,
            'known_cost_eur':str(sum((Decimal(r['cost_microeur'][arm])/1_000_000 for r in comparisons
                                   if type(r['cost_microeur'][arm]) is int),Decimal(0))),
            'cost_unknown':sum(r['cost_microeur'][arm] is None for r in comparisons)}
    return {'schema_version':'decision-evidence-report-v1','protocol_id':PROTOCOL_ID,'protocol':PROTOCOL,
        'as_of':report['as_of'],'evaluation_day':aware(report['as_of']).date().isoformat(),
        'source_protocol_id':report['protocol_id'],'source_report_sha256':digest(report),
        'dataset_kind':report['dataset_kind'],'trade_authorized':False,'strategy_input':False,'model_calls':0,
        'source_cohorts':len(rows),'trace_counts':dict(Counter(r['trace_reason'] for r in traces)),
        'population_count':len(comparisons),'arms':arms,'traces':traces,'comparison_rows':comparisons,
        'note':'Selection counterfactual on common code-only reference outcomes, not a single-reviewer executable return. '
               'Reuse an existing independent assessment; no extra AI calls. Different arms overlap; do not add them. '
               'Stage duration excludes preparation/revalidation; no latency saving is assumed. '
               'Current prompt revision only; first attempted asset/day retained even when incomplete. '
               'Costs use observed call allocation where available. Unresolved/unfilled/open outcomes stay separate. '
               'Reference spread alone does not establish broker spread or a profitable missed trade.'}


def bounded(report):
    from copy import deepcopy
    from .candidate_packages import canonical
    value=deepcopy(report);value['traces_omitted']=0;value['comparison_rows_omitted']=0
    while len(canonical(value).encode())>170000:
        key='traces' if value['traces'] else 'comparison_rows'
        if not value[key]:raise ValueError('decision_evidence_capacity')
        value[key].pop();value[key+'_omitted']+=1
    return value
