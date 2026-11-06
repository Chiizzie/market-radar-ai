"""Internal run explanations from existing artifacts; never calls models or orders."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import re

CONDITIONS = {'below_rolling_vwap', 'nonpositive_momentum', 'relative_volume_below_1_5',
              'conditional_entry_already_passed', 'entry_trigger_already_reached_rebuild',
              'setup_invalidated_before_entry', 'conditional_setup_not_formed'}
RISK = {'risk_limit_or_arithmetic', 'net_reward_below_2r', 'paper_capital_exceeded',
        'invalid_expiry_or_overnight', 'outside_entry_or_exit_window', 'exit_after_market_deadline'}
ZERO_STATES = {'no_qualified_candidate_zero_cost','paper_review_cooldown','paper_watcher_disabled_zero_cost',
               'paper_setup_already_attempted','budget_deferred','waiting_for_stock_history_zero_cost'}


def label(value):
    # Artifact strings must not inject Markdown, links, HTML or log instructions.
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_:.-]{1,120}',value) else 'unknown'


def category(reason):
    if reason in CONDITIONS:return 'setup_conditions'
    if reason in RISK:return 'risk_or_time_rules'
    if reason=='market_session_not_confirmed':return 'session_unconfirmed_or_closed'
    if reason in {'unusable_or_stale','insufficient_history','no_baseline_participation','mixed_quote_currency'}:
        return 'capture_quality_or_history'
    return 'evidence_or_validation_gap'


def read(path, issues):
    if not path.exists():return None
    try:
        if path.stat().st_size>4_000_000:raise ValueError()
        value=json.loads(path.read_text())
        if not isinstance(value,dict):raise ValueError()
        return value
    except (OSError,ValueError,UnicodeError):
        issues.append(path.name);return None


def spending(packet, status, audit, *, budget_loader=None, phase='review'):
    unknown={'status':'unavailable','settled_estimated_eur':None,'held_maximum_eur':None,
             'generation_records':None,'reconciliation_required':True}
    if phase=='collection':
        return {'status':'collection_has_no_model_access','settled_estimated_eur':'0','held_maximum_eur':'0',
                'generation_records':0,'reconciliation_required':False}
    if not audit and not packet and status.get('state') in ZERO_STATES and status.get('model_calls')==0:
        return {'status':'confirmed_zero_model_calls','settled_estimated_eur':'0','held_maximum_eur':'0',
                'generation_records':0,'reconciliation_required':False}
    pid=packet.get('packet_id')
    if not isinstance(pid,str) or not re.fullmatch('[a-f0-9]{64}',pid) or budget_loader is None:return unknown
    try:
        from ..agents.github_budget import validate_state
        from ..agents.candidate_packages import digest
        if digest(packet['packet'])!=pid:return unknown
        state,_=budget_loader();state=validate_state(state)
        prefix='paper-final-v1:'+pid+':'
        rows=[e for k,e in state['entries'].items() if k.startswith(prefix)]
        settled=sum(e['actual'] for e in rows if e['actual'] is not None)
        held=sum(e['reserved'] for e in rows if e['actual'] is None)
        return {'status':'ledger_has_unsettled_reservations' if held else 'ledger_reconciled',
                'settled_estimated_eur':str(Decimal(settled)/1_000_000),
                'held_maximum_eur':str(Decimal(held)/1_000_000),
                'generation_records':sum(e['usage'] is not None for e in rows),
                'reconciliation_required':bool(held)}
    except Exception:
        return unknown  # No provider bodies, secrets or exception strings in reports.


def build_report(collection, review=None, *, now, budget_loader=None):
    issues=[];collection=Path(collection);phase='review' if review is not None else 'collection'
    root=Path(review) if review is not None else collection
    q=read(root/'qualification.json',issues)
    origin=phase
    if q is None and phase=='review':q=read(collection/'qualification.json',issues);origin='collection_fallback_not_review_confirmation'
    q=q or {};status=read(root/'status.json',issues) or {}
    audit=(read(root/'review.json',issues) or {}) if phase=='review' else {}
    packet=(read(root/'packet.json',issues) or {}) if phase=='review' else {}
    selection=(read(root/'review-selection.json',issues) or {}) if phase=='review' else {}
    coverage={};candidates=[];reasons=Counter();groups=Counter()
    for market,entry in q.get('selection',{}).get('markets',{}).items():
        coverage[label(market)]={k:entry.get(k) for k in ('attempted','rankable','shortlisted','deferred_by_limit')}
        for rejected in entry.get('rejected',[]):
            reason=label(rejected.get('reason'));reasons[reason]+=1;groups[category(reason)]+=1
            candidates.append({'candidate_id':label(market+':'+rejected.get('symbol','unknown')),
                               'stage':'capture_rejected','blockers':[reason],'ready_for_review':False})
    for row in q.get('candidates',[]):
        blocks=sorted({label(b) for b in row.get('paper_blockers',[])})
        for reason in blocks:reasons[reason]+=1;groups[category(reason)]+=1
        candidates.append({'candidate_id':label(row.get('candidate_id')),'stage':'qualified_screening',
                           'blockers':blocks,'ready_for_review':row.get('eligible_for_paper_review') is True and not blocks})
    calls=audit.get('calls',[])
    from ..agents.paper_verdict import STAGES
    result=audit.get('result') or {}
    complete=False
    try:
        from ..agents.paper_verdict import VerdictReview
        from ..agents.candidate_packages import digest
        reviews=[VerdictReview.model_validate(r) for r in result.get('reviews',[])]
        complete=(digest(packet['packet'])==packet['packet_id']==result['packet_id']
                  and result['schema_version']=='paper-ai-review-v1' and result['trade_authorized'] is False
                  and [r.stage for r in reviews]==STAGES
                  and all(r.packet_id==packet['packet_id'] and set(r.source_ids)<=set(packet['packet']['source_ids'])
                          and len(set(r.source_ids))==len(r.source_ids)
                          and list(r.reviewed_stages)==(STAGES[:i] if i>=6 else []) for i,r in enumerate(reviews)))
    except (KeyError,ValueError,TypeError):pass
    decision=(read(root/'decision.json',issues) or {}) if phase=='review' else {}
    delivery=read(root/'delivery.json',issues) or {}
    discovery=read(collection/'discovery.json',issues) or {}
    money=spending(packet,status,audit,budget_loader=budget_loader,phase=phase)
    return {'schema_version':'internal-run-diagnostics-v1','generated_at_dublin':now.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
            'phase':phase,'qualification_origin':origin,'qualification_available':bool(q),
            'discovery':{'discovered_count':discovery.get('discovered_count'),
                         'fallback_used':discovery.get('fallback_used'),
                         'failures':[label(x) for x in discovery.get('failures',[])]},
            'coverage':coverage,'candidates':candidates,'blocker_counts':dict(sorted(reasons.items())),
            'blocker_groups':dict(sorted(groups.items())),
            'review':{'state':label(status.get('state','not_confirmed')),
                      'selected_candidate':label(selection.get('selected_candidate_id') or packet.get('packet',{}).get('candidate_id')),
                      'validated_eight_stage_review':complete,
                      'final_verdict':label(decision.get('verdict','not_confirmed')),
                      'final_blockers':[label(x) for x in decision.get('blockers',[])],
                      'stages_with_assessments':sum(isinstance(c.get('assessment'),dict) for c in calls),
                      'stages_started':len(calls),'last_stage':label(calls[-1].get('stage')) if calls else None,
                      'skipped':[{'candidate_id':label(x.get('candidate_id')),'reason':label(x.get('reason'))} for x in selection.get('skipped',[])],
                      'dashboard_delivery':label(delivery.get('dashboard',delivery.get('state','not_confirmed'))),
                      'telegram_delivery':label(delivery.get('telegram','not_confirmed'))},
            'spending':money,'unreadable_artifacts':issues,'model_calls_by_diagnostics':0,'trade_authorized':False,
            'note':'Internal diagnostics, not trade advice. Blocker counts overlap per candidate. Eligibility is not approval. Unknown costs are not zero; ledger figures are estimates, not an invoice.'}


def markdown(report):
    lines=['## Market Radar run diagnostics', '', report['generated_at_dublin'], '',
           f"Phase: {report['phase']}; qualification source: {report['qualification_origin']}.",
           f"Review: {report['review']['state']}; validated eight-stage review: {report['review']['validated_eight_stage_review']}.",
           f"Assessments received: {report['review']['stages_with_assessments']} / 8.",
           f"Final paper verdict: {report['review']['final_verdict']}; blockers: {', '.join(report['review']['final_blockers']) or 'None recorded'}.",
           f"Dashboard delivery: {report['review']['dashboard_delivery']}; Telegram: {report['review']['telegram_delivery']}.", '']
    money=report['spending']
    lines.append('AI cost: unavailable; reconciliation required.' if money['settled_estimated_eur'] is None else
                 f"AI cost estimate recorded: EUR {money['settled_estimated_eur']}; unresolved reservation maximum: EUR {money['held_maximum_eur']}.")
    lines+=['', 'Blocker groups (overlap per candidate): '+(', '.join(f'{k}: {v}' for k,v in report['blocker_groups'].items()) or 'None recorded'), '', '| Candidate | Screening | Blockers |', '|---|---|---|']
    for row in report['candidates']:
        lines.append(f"| {row['candidate_id']} | {'Ready for review only' if row['ready_for_review'] else row['stage']} | {', '.join(row['blockers']) or 'None at screening'} |")
    for skipped in report['review']['skipped']:
        lines.append(f"Skipped review: {skipped['candidate_id']} — {skipped['reason']}.")
    lines+=['', 'Blockers are grouped in the JSON artifact; conditions and evidence gaps are reported separately.',
            'Missing captures, incomplete reviews and unknown spending must not be treated as successful trade calls.','']
    return '\n'.join(lines)


def main():
    import argparse,os
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection',type=Path,required=True);p.add_argument('--review',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--summary',type=Path)
    args=p.parse_args();loader=None
    if args.review is not None and os.environ.get('GH_BUDGET_TOKEN'):
        from ..agents.github_budget import GitHubBudgetStore
        loader=GitHubBudgetStore(os.environ['GH_BUDGET_TOKEN']).load
    report=build_report(args.collection,args.review,now=datetime.now(timezone.utc),budget_loader=loader)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if args.summary:
        with args.summary.open('a') as f:f.write(markdown(report))
    print(json.dumps({'diagnostics_written':True,'model_calls':0,'qualification_available':report['qualification_available']}))


if __name__=='__main__':main()
