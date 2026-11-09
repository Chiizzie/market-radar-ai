"""Internal run explanations from existing artifacts; never calls models or orders."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import re
from ..market_data.limits import STOCK_SCREEN_LIMIT, STOCK_RESEARCH_LIMIT

CONDITIONS = {'below_rolling_vwap', 'nonpositive_momentum', 'relative_volume_below_1_5',
              'conditional_entry_already_passed', 'entry_trigger_already_reached_rebuild',
              'setup_invalidated_before_entry', 'conditional_setup_not_formed'}
RISK = {'risk_limit_or_arithmetic', 'net_reward_below_2r', 'paper_capital_exceeded',
        'invalid_expiry_or_overnight', 'outside_entry_or_exit_window', 'exit_after_market_deadline'}
ZERO_STATES = {'no_qualified_candidate_zero_cost','paper_review_cooldown','paper_watcher_disabled_zero_cost',
               'paper_setup_already_attempted','budget_deferred','waiting_for_stock_history_zero_cost'}
DISCOVERY_COUNTS = ('catalogue_candidates', 'fresh_activity_leads', 'candidate_pool',
                    'technical_checked', 'technical_usable', 'technical_unavailable',
                    'technical_deferred', 'research_selected', 'research_deferred')


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


def discovery_summary(discovery, *, now):
    """Only export bounded counts and known metadata; never raw catalogue records."""
    def count(value, maximum=20_200):
        return value if type(value) is int and 0 <= value <= maximum else None

    failures = discovery.get('failures', [])
    summary = {
        'discovered_count': count(discovery.get('discovered_count')),
        'fallback_used': discovery.get('fallback_used') if type(discovery.get('fallback_used')) is bool else None,
        'failures': [label(x) for x in failures[:50]] if isinstance(failures, list) else ['unknown'],
        'coverage_status': 'unavailable', 'coverage': None,
        'universe': {'source': 'unknown', 'retrieved_at': None, 'cache_status': 'unavailable',
                     'freshness': 'unavailable', 'account_permission_verified': False},
    }
    source = discovery.get('coverage')
    if source is not None:
        summary['coverage_status'] = 'invalid'
        if isinstance(source, dict):
            counts = {k: count(source.get(k)) for k in DISCOVERY_COUNTS}
            if (all(v is not None for v in counts.values())
                    and counts['catalogue_candidates'] <= 20_000
                    and counts['fresh_activity_leads'] <= 200
                    and counts['technical_checked'] <= STOCK_SCREEN_LIMIT
                    and counts['research_selected'] <= STOCK_RESEARCH_LIMIT
                    and counts['technical_checked'] == counts['technical_usable'] + counts['technical_unavailable']
                    and counts['candidate_pool'] == counts['technical_checked'] + counts['technical_deferred']
                    and counts['candidate_pool'] == counts['research_selected'] + counts['research_deferred']):
                summary['coverage_status'] = 'validated'
                summary['coverage'] = counts
    universe = discovery.get('universe')
    reasons = discovery.get('selection_reason_counts')
    if (isinstance(reasons, dict) and summary['coverage']
            and all(type(v) is int and 0 <= v <= 20200 for v in reasons.values())
            and sum(reasons.values()) == summary['coverage']['candidate_pool']):
        summary['selection_reason_counts'] = {label(k):v for k,v in reasons.items()}
    if isinstance(universe, dict) and universe.get('source') == 'trading212_metadata':
        metadata = summary['universe']
        metadata['source'] = 'trading212_metadata'
        if universe.get('cache_status') in ('refreshed', 'reused', 'unavailable'):
            metadata['cache_status'] = universe['cache_status']
        if universe.get('freshness') in ('fresh', 'stale_but_valid', 'unavailable'):
            metadata['freshness'] = universe['freshness']
        try:
            stamp = datetime.fromisoformat(universe['retrieved_at'])
            if stamp.tzinfo is not None and stamp <= now:
                metadata['retrieved_at'] = stamp.isoformat()
        except (KeyError, TypeError, ValueError):
            pass
        if metadata['retrieved_at'] is None:
            metadata['cache_status'] = metadata['freshness'] = 'unavailable'
    return summary


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
                           'strategy_id':label(row.get('technical_checks', {}).get('strategy_id')),
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
    from .missed_moves import explain
    from ..market_data.catalyst_links import routing_report
    missed=explain(read(collection/'discovery-selection.json',issues) or {},q,decision,selection,now=now)
    return {'schema_version':'internal-run-diagnostics-v1','generated_at_dublin':now.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
            'phase':phase,'qualification_origin':origin,'qualification_available':bool(q),
            'discovery':discovery_summary(discovery, now=now),
            'missed_moves':missed,
            'catalyst_links':routing_report(discovery.get('catalyst_links',{}),read(collection/'discovery-selection.json',issues) or {},q),
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
            'budget_headroom':read(root/'budget-headroom.json',issues),'spending':money,'unreadable_artifacts':issues,'model_calls_by_diagnostics':0,'trade_authorized':False,
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
    budget=report.get('budget_headroom')
    if isinstance(budget,dict):
        lines.append('AI review reserve required: EUR 0.15. Spending allowance is separate from provider account credit.')
        for period,row in budget.get('periods',{}).items():
            if period not in ('daily','monthly','lifetime'):continue
            try:
                values=[str(Decimal(row[k])) for k in ('limit_eur','spent_eur','held_eur','remaining_eur')]
                if not all(Decimal(v).is_finite() for v in values):continue
            except Exception:continue
            lines.append(f'{period}: limit EUR {values[0]}; already spent EUR {values[1]}; held EUR {values[2]}; remaining EUR {values[3]}.')
    discovery = report['discovery']
    counts = discovery['coverage']
    if counts is None:
        lines += ['', 'Discovery coverage counts: unavailable or invalid; no broad-coverage claim.']
    else:
        metadata = discovery['universe']
        lines += ['', 'Stock discovery coverage (catalogue metadata is not account buying permission):', '',
                  '| Measure | Stocks |', '|---|---:|',
                  f"| Catalogue candidates | {counts['catalogue_candidates']} |",
                  f"| Fresh activity/mover leads | {counts['fresh_activity_leads']} |",
                  f"| Combined candidate pool | {counts['candidate_pool']} |",
                  f"| Technical checks attempted | {counts['technical_checked']} |",
                  f"| Technically usable / unavailable | {counts['technical_usable']} / {counts['technical_unavailable']} |",
                  f"| Technical checks deferred | {counts['technical_deferred']} |",
                  f"| Selected for detailed research / deferred | {counts['research_selected']} / {counts['research_deferred']} |", '',
                  f"Catalogue: {metadata['cache_status']}; freshness: {metadata['freshness']}; source retrieved at: {metadata['retrieved_at'] or 'unavailable'}.",
                  'These counts describe this run. Selected for research does not mean technically checked, AI reviewed or approved.']
    if discovery.get('selection_reason_counts'):
        lines += ['', 'Selection decisions: '+', '.join(f'{k}: {v}' for k,v in discovery['selection_reason_counts'].items()),
                  'Per-symbol scores, snapshot freshness, selection lanes and skip reasons: `discovery-selection.json` in the capture artifact.']
    lines+=['', 'Blocker groups (overlap per candidate): '+(', '.join(f'{k}: {v}' for k,v in report['blocker_groups'].items()) or 'None recorded'), '', '| Candidate | Strategy | Screening | Blockers |', '|---|---|---|---|']
    for row in report['candidates']:
        lines.append(f"| {row['candidate_id']} | {row.get('strategy_id', 'unknown')} | {'Ready for review only' if row['ready_for_review'] else row['stage']} | {', '.join(row['blockers']) or 'None at screening'} |")
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
    args.output.with_name('missed-moves.json').write_text(json.dumps(report['missed_moves'],indent=2)+'\n')
    args.output.with_name('competitor-catalysts.json').write_text(json.dumps(report['catalyst_links'],indent=2)+'\n')
    if args.summary:
        with args.summary.open('a') as f:
            f.write(markdown(report))
            f.write('\n### Related-company catalyst research\n\n')
            links = report['catalyst_links']
            f.write('Bounded semiconductor discovery; indirect hypotheses, not trade calls. Full evidence: competitor-catalysts.json.\n')
            for row in links.get('rows',[])[:12]:
                f.write('- '+label(row['source_symbol'])+' → '+label(row['symbol'])+': '+label(row['response']['state'])+'; '+label(row['admission_state'])+'; '+', '.join(label(b) for b in row['qualification_blockers'])+'\n')
            f.write('\n### Observed movers and coverage gaps\n\n')
            for row in report['missed_moves']['rows'][:15]:
                f.write('- '+label(row['symbol'])+': '+', '.join(label(x) for x in row['reasons'])+'\n')
            f.write('\nThese are routing explanations, not proven missed profits. Full details: missed-moves.json.\n')
    print(json.dumps({'diagnostics_written':True,'model_calls':0,'qualification_available':report['qualification_available']}))


if __name__=='__main__':main()
