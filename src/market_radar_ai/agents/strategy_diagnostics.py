"""Explain the frozen experiment without changing its admissions or outcomes."""
import json
from collections import Counter
from decimal import Decimal
from statistics import median
from .candidate_packages import digest, canonical
from .paper_comparison import aware
from .strategy_experiment import PROTOCOL_ID as SOURCE_PROTOCOL, VARIANTS, num, text

PROTOCOL={'version':'strategy-diagnostics-v1','source_protocol_id':SOURCE_PROTOCOL,
          'strategy_input':False,'extra_model_calls':0,'prices':'observed_IEX_only'}
PROTOCOL_ID=digest(PROTOCOL)


def input_trace(source,now):
    """Keep the observed rejection context; never infer an earlier crossing."""
    from ..market_data.stock_checks import evaluate
    result={'candidate_id':'stocks:'+source['symbol'],'evaluated_at':aware(now).isoformat()}
    try:
        rows=source['candles'][-20:]
        ref=next(r for r in evaluate(source['reference_checks'],now=now)['stocks'] if r['symbol']==source['symbol'])
        result.update(reference_quote_status=ref.get('quote_status'),spread_bps=ref.get('spread_bps'),
                      bid_usd=ref.get('bid'),ask_usd=ref.get('ask'),
                      bars_received_at=source.get('bars_received_at'),bar_count=len(rows))
        if len(rows)>=6:
            entry=max(num(r['high']) for r in rows[-6:-1])*Decimal('1.001')
            ask=num(ref['ask'])
            result.update(trigger_usd=text(entry),ask_minus_trigger_bps=text((ask/entry-1)*10000),
                          last_bar_at=rows[-1]['timestamp'],
                          last_bar_age_seconds=(aware(now)-aware(rows[-1]['timestamp'])).total_seconds())
        result['assessment']='observed_reference_only_no_broker_comparison'
    except (ValueError,KeyError,TypeError,StopIteration,ArithmeticError):
        result['assessment']='trace_inputs_incomplete'
    return result


def build(worker,now):
    outcomes=worker.outcomes(now);by_symbol={}
    for q in worker.quotes:by_symbol.setdefault(q['candidate_id'],[]).append(q)
    variants={};closed_rows=[]
    for name in VARIANTS:
        blocks=Counter();caps=Counter();rr=[];target_atr=[];closed_reasons=Counter()
        for key,c in worker.cohorts.items():
            v=c['variants'][name];p=v['plan'];f=c['features'];result=outcomes[key][name]
            blocks.update(v['blockers'])
            entry,stop,target,atr=map(num,(p['entry_usd'],p['stop_usd'],p['target_usd'],f['atr14_usd']))
            rr.append(num(p['net_rr']));target_atr.append((target-entry)/atr)
            if 'net_reward_below_2r' in v['blockers']:
                resistance=num(f['resistance_usd']) if f.get('resistance_usd') else None
                cap=('observed_resistance' if resistance is not None and abs(target-resistance)<Decimal('.000001') else
                     'six_ATR_projection' if abs(target-(entry+6*atr))<Decimal('.000001') else 'three_stop_distances')
                caps[cap]+=1
            if result['state']=='closed':
                closed_reasons[result['reason']]+=1
                prices=[num(q['native_quote_usd']['bid']) for q in by_symbol.get(c['candidate_id'],[])
                        if aware(result['entry_at'])<=aware(q['received_at'])<=aware(result['exit_at'])
                        and aware(q['quote']['observed_at'])>=aware(result['entry_at'])]
                fill=num(result['entry_usd']);risk=entry-stop
                closed_rows.append({'candidate_id':c['candidate_id'],'setup_id':key,'variant':name,
                    'reason':result['reason'],'entry_at':result['entry_at'],'exit_at':result['exit_at'],
                    'holding_seconds':(aware(result['exit_at'])-aware(result['entry_at'])).total_seconds(),
                    'net_pnl_eur':result['net_pnl_eur'],'planned_risk_eur':p['planned_loss_eur'],
                    'stop_distance_ATR':text(risk/atr),'target_distance_ATR':text((target-entry)/atr),
                    'observed_bid_favorable_R':text((max(prices)-fill)/risk) if prices else None,
                    'observed_bid_adverse_R':text((min(prices)-fill)/risk) if prices else None,
                    'path_quotes':len(prices)})
        variants[name]={'cohorts':len(worker.cohorts),'blocker_counts':dict(blocks),
                        'net_reward_target_caps':dict(caps),'median_net_rr':text(median(rr)) if rr else None,
                        'median_target_distance_ATR':text(median(target_atr)) if target_atr else None,
                        'closed_exit_reasons':dict(closed_reasons),
                        'states':dict(Counter(v[name]['state'] for v in outcomes.values()))}
    screens=[json.loads(e['payload_json']) for e in worker.source if e['kind']=='strategy_screen']
    screening_counts=Counter()
    for s in screens:screening_counts.update(s['reasons'])
    return {'schema_version':'strategy-diagnostics-report-v1','protocol_id':PROTOCOL_ID,'protocol':PROTOCOL,
        'source_protocol_id':SOURCE_PROTOCOL,'as_of':aware(now).isoformat(),'evaluation_day':worker.day,
        'dataset_kind':'forward','trade_authorized':False,'strategy_input':False,'model_calls':0,
        'cohort_count':len(worker.cohorts),'source_event_count':len(worker.source),
        'source_events_sha256':digest(worker.source),'screen_count':len(screens),
        'screening_blocker_occurrences':dict(screening_counts),'variants':variants,'closed_rows':closed_rows,
        'latest_input_trace':getattr(worker,'screen_trace',[]),
        'note':'Diagnostics on the unchanged frozen protocol. Screening occurrences repeat symbols; they are not unique missed trades. '
               'Quoted excursions sample available reference bids only, not intrapoll highs/lows or broker fills. '
               'Target caps and costs explain a gate, not whether taking a rejected trade would profit. '
               'Control targets are expanded arithmetically; ATR targets are capped. '
               'Risk variants change both stop and target construction. Keep outcomes and uncertainties separate.'}


def bounded(value):
    from copy import deepcopy
    value=deepcopy(value);value['closed_rows_omitted']=0;value['latest_input_trace_omitted']=0
    while len(canonical(value).encode())>170000:
        key='closed_rows' if value['closed_rows'] else 'latest_input_trace'
        if not value[key]:raise ValueError('strategy_diagnostics_capacity')
        value[key].pop();value[key+'_omitted']+=1
    return value
