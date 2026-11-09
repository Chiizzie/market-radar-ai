"""Observed movers and routing reasons, never counterfactual profits or trade advice."""
from collections import Counter
from decimal import Decimal
from zoneinfo import ZoneInfo
from ..market_data.coverage_lanes import CORE


def explain(manifest, qualification, decision, selection, *, now):
    candidates={r['candidate_id']:r for r in qualification.get('candidates',[])}
    rejected={market+':'+r['symbol']:r.get('reason','unavailable') for market,m in qualification.get('selection',{}).get('markets',{}).items() for r in m.get('rejected',[])}
    rows=[];local=now.astimezone(ZoneInfo('America/New_York'))
    early=local.weekday()<5 and (9,30)<=(local.hour,local.minute)<(10,0)
    for m in manifest.get('symbols',[]):
        symbol=m.get('symbol');cid='stocks:'+str(symbol)
        try: change=Decimal(str(m.get('day_change_pct',0))); acceleration=Decimal(str(m.get('acceleration_pct',0)))
        except (ValueError,ArithmeticError):continue
        if not change.is_finite() or not acceleration.is_finite():continue
        if symbol not in CORE and not (m.get('snapshot_status')=='fresh' and (change>=2 or acceleration>=Decimal('.5'))):continue
        q=candidates.get(cid); reasons=[]
        if not m.get('detail_selected'): reasons.append('not_examined_in_detail')
        elif early:reasons.append('too_early_for_main_strategy')
        elif q:
            blocks=q.get('paper_blockers',[])
            if any(x in blocks for x in ('conditional_entry_already_passed','entry_trigger_already_reached_rebuild')):reasons.append('entry_trigger_already_passed')
            if blocks: reasons.append('failed_qualification')
            elif decision.get('candidate_id')==cid:
                if decision.get('verdict')=='PAPER_WATCH_FOR_ENTRY':reasons.append('approved_paper_watch_not_confirmed_fill')
                if 'team_did_not_clear_setup' in decision.get('blockers',[]):reasons.append('ai_did_not_clear_setup')
                if any(b!='team_did_not_clear_setup' for b in decision.get('blockers',[])):reasons.append('post_review_validation_failed')
            elif selection.get('selected_candidate_id'):reasons.append('not_selected_for_paid_review')
            else:reasons.append('qualified_review_not_confirmed')
        else:reasons.append('capture_or_shortlist_rejected' if cid in rejected else 'qualification_not_available')
        rows.append({'symbol':symbol,'snapshot_status':m.get('snapshot_status'),'observed_at':m.get('observed_at'),
            'day_change_pct':float(change),'acceleration_pct':float(acceleration),
            'detail_selected':m.get('detail_selected',False),'detail_lane':m.get('detail_lane'),
            'selection_reason':m.get('selection_reason'),'reasons':reasons,
            'qualification_blockers':q.get('paper_blockers',[]) if q else [rejected[cid]] if cid in rejected else [],
            'decision_blockers':decision.get('blockers',[]) if decision.get('candidate_id')==cid else []})
    rows.sort(key=lambda r:(r['symbol'] not in CORE,-r['day_change_pct'],r['symbol']))
    return {'schema_version':'missed-move-diagnostics-v1','as_of':now.isoformat(),
        'observed_movers_and_core_count':len(rows),'rows':rows[:100],'rows_omitted':max(0,len(rows)-100),
        'reason_counts':dict(Counter(b for r in rows for b in r['reasons'])),
        'trade_authorized':False,'model_calls':0,
        'note':'Current captured routing evidence only; day changes can include overnight gaps. Not proof of a tradable missed opportunity or profit. Deferred candidates were not fully assessed. Snapshot scope and time apply.'}
