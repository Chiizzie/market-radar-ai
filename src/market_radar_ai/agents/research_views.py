"""Read-only projections for history, setup detail and hypothetical exposure.

These are reporting additions, never new trading gates or protocol parameters.
Alternative experiment arms are measured separately and are never added together.
"""
from collections import defaultdict
from decimal import Decimal

from .candidate_packages import canonical, digest
from .paper_comparison import aware

D=Decimal


def public_plan(plan):
    if plan is None: return None
    keys=('currency','entry_eur','stop_eur','target_eur','quantity',
          'assumed_round_trip_cost_eur','expires_at','exit_by')
    out={k:plan[k] for k in keys}
    for k in ('entry_eur','stop_eur','target_eur','quantity','assumed_round_trip_cost_eur'):
        out[k]=format(D(out[k]),'f')
    out['planned_loss_eur']=format((D(out['entry_eur'])-D(out['stop_eur']))*D(out['quantity'])+D(out['assumed_round_trip_cost_eur']),'f')
    return out


def public_outcome(outcome):
    if outcome is None: return None
    result=dict(outcome)
    for k in ('entry_fill','exit_fill','net_pnl_eur'):
        if result.get(k) is not None: result[k]=format(D(result[k]),'f')
    return result


def exposure(rows, arm, *, now):
    """Notional plus separate initial loss-to-stop; unresolved is possible exposure.

    Closed positions release capital at their observed exit. At equal timestamps,
    exits release before entries. Instant round trips consume one allocation but
    do not stack with other instant round trips at an indistinguishable timestamp.
    Missing entry/exit evidence is not silently treated as a closed position.
    """
    current=D(0); risk=D(0); possible=D(0); possible_risk=D(0); pending=D(0)
    opened=unresolved=watching=0; events=[]; symbols=defaultdict(Decimal)
    for row in rows:
        a=row['arms'].get(arm)
        if not a or a['plan'] is None: continue
        p=a['plan']; q=D(p['quantity']); cost=D(p['assumed_round_trip_cost_eur'])
        o=a['outcome'] or {}; state=a['state']
        if state=='watching':
            watching+=1;pending+=D(p['entry_eur'])*q+cost
        if o.get('entry_fill') is None or not o.get('entry_at'): continue
        capital=D(o['entry_fill'])*q+cost
        initial_risk=max(D(0),(D(o['entry_fill'])-D(p['stop_eur']))*q+cost)
        if state=='open_simulation':
            opened+=1;current+=capital;risk+=initial_risk;symbols[row['candidate_id']]+=capital
        elif state=='unresolved':
            unresolved+=1;possible+=capital;possible_risk+=initial_risk
        start=aware(o['entry_at']); end=aware(o['exit_at']) if o.get('exit_at') else None
        if end is None:
            events.append((start,1,capital,initial_risk))
        elif end>start:
            events.extend([(start,1,capital,initial_risk),(end,0,-capital,-initial_risk)])
        elif end==start:
            events.append((start,.5,capital,initial_risk))
    capital=loss=peak_capital=peak_risk=D(0); active=peak_count=0
    for _,kind,delta,delta_risk in sorted(events):
        if kind==.5:
            peak_capital=max(peak_capital,capital+delta);peak_risk=max(peak_risk,loss+delta_risk);peak_count=max(peak_count,active+1)
            continue
        capital+=delta;loss+=delta_risk;active+=1 if kind else -1
        peak_capital=max(peak_capital,capital);peak_risk=max(peak_risk,loss);peak_count=max(peak_count,active)
    return {'open_positions':opened,'open_entry_capital_eur':format(current,'f'),'open_initial_risk_eur':format(risk,'f'),
        'unresolved_positions':unresolved,'unresolved_possible_capital_eur':format(possible,'f'),
        'unresolved_possible_initial_risk_eur':format(possible_risk,'f'),'watching_positions':watching,
        'watching_planned_capital_eur':format(pending,'f'),'peak_assumed_concurrent_positions':peak_count,
        'peak_assumed_concurrent_capital_eur':format(peak_capital,'f'),'peak_assumed_concurrent_initial_risk_eur':format(peak_risk,'f'),
        'largest_open_symbol_capital_eur':format(max(symbols.values(),default=D(0)),'f'),
        'capital_limit_enforced':False,'portfolio_return_established':False}


def comparison_rows(report):
    rows=[]
    for r in report['rows']:
        arms={}
        for arm in ('code_only','ai_reviewed'):
            a=r[arm]
            arms[arm]={'state':a['state'],'outcome':public_outcome(a['outcome']),
                'observations_available':a.get('observations_available',0),
                'plan':public_plan(r['plans'][arm])}
        rows.append({'setup_id':r['setup_id'],'candidate_id':r['candidate_id'],'strategy_id':r['strategy_id'],
            'enrolled_at':r['enrolled_at'],'review_started_at':r['review_started_at'],
            'decision_at':r['decision_at'],'decision_blockers':r['decision_blockers'],
            'ai_cost':r['ai_cost'],'arms':arms})
    return rows


def method_rows(worker, *, now):
    rows=[]
    for r in worker.outcomes(now):
        s=worker.cohorts[r['setup_id']]
        rows.append({'setup_id':r['setup_id'],'candidate_id':r['candidate_id'],'strategy_id':s['strategy_id'],
            'enrolled_at':r['enrolled_at'],'review_started_at':None,'decision_at':None,'decision_blockers':None,
            'ai_cost':{'settled_microeur':0,'held_microeur':0,'complete':True,'recorded_at':aware(now).isoformat()},
            'arms':{'method_shadow':{'state':r['state'],'outcome':public_outcome(r['outcome']),
                'observations_available':r['observations_available'],'plan':public_plan(s['plan'])}}})
    return rows


def publication(report, rows):
    if report['dataset_kind']!='forward' or report['trade_authorized'] is not False:
        raise ValueError('forward_publication_only')
    if len(rows)!=report['cohort_count'] or len({r['setup_id'] for r in rows})!=len(rows):
        raise ValueError('detail_cohort_mismatch')
    summary={k:v for k,v in report.items() if k not in ('rows','matched_observed_pairs')}
    arms=('code_only','ai_reviewed') if report['schema_version']=='paper-comparison-report-v1' else ('method_shadow',)
    summary['exposure']={a:exposure(rows,a,now=aware(report['as_of'])) for a in arms}
    summary['exposure_note']='Independent hypothetical allocations. Arms are alternatives; do not add them together. '
    summary['exposure_note']+='Capital includes estimated round-trip costs; risk is the initial loss to the original stop, not a guaranteed loss cap. '
    summary['exposure_note']+='Unresolved positions may remain exposed. Peaks include that uncertainty; no account capital limit or sector correlation is modelled.'
    if len(rows)>2000:
        summary['details']={'snapshot_id':None,'storage_id':None,'count':len(rows),'complete':False,'reason':'detail_capacity_exceeded'}
        return summary,[]
    snapshot=digest({'protocol':report['protocol_id'],'day':report['evaluation_day'],'as_of':report['as_of'],'rows':rows})
    storage=digest({'kind':'research-views-v1','protocol_id':report['protocol_id']})
    summary['details']={'snapshot_id':snapshot,'storage_id':storage,'count':len(rows),'complete':True,'reason':None}
    details=[{'schema_version':'research-setup-report-v1','protocol_id':report['protocol_id'],
        'storage_id':storage,
        'evaluation_day':report['evaluation_day'],'as_of':report['as_of'],'snapshot_id':snapshot,
        'dataset_kind':'forward','trade_authorized':False,**r} for r in rows]
    return summary,details


def append_publication(client, experiment, report, rows, *, clock):
    from .comparison_live import envelope
    summary,details=publication(report,rows)
    batch=[];size=0
    for detail in details:
        e=envelope('setup_report',detail,aware(report['as_of']));length=len(canonical(e).encode())
        if length>175000: raise ValueError('detail_payload_capacity')
        if size+length>1_500_000 or len(batch)==100:
            client.append(summary['details']['storage_id'],batch);batch=[];size=0
        batch.append(e);size+=length
    client.append(summary['details']['storage_id'],batch)
    # Commit the visible summary last: a failed partial batch is never presented
    # as a complete detail snapshot. Old summaries retain their own immutable rows.
    kind='report' if report['schema_version']=='paper-comparison-report-v1' else 'method_report'
    client.append(experiment,[envelope(kind,summary,aware(report['as_of']))])
    return summary
