"""Describe observed IEX coverage without inventing bars or inferring a halt."""
from collections import Counter


def describe(result, checked, *, now):
    rows=sorted(getattr(result,"candles",[]),key=lambda r:r.timestamp)[-60:]
    gaps=[int((b.timestamp-a.timestamp).total_seconds()) for a,b in zip(rows,rows[1:]) if (b.timestamp-a.timestamp).total_seconds()>450]
    codes=sorted({x.get('code','unknown') for x in checked.get('quality_issues',[])})
    if getattr(result,'status','unknown')!='ok':category='provider_or_payload_failure'
    elif not rows:category='no_completed_iex_bars'
    elif 'stale_candle' in codes:category='stale_iex_tail'
    elif gaps:category='gapped_iex_history'
    elif codes:category='other_quality_failure'
    else:category='usable_iex_history'
    tail=0
    for i in range(len(rows)-1,-1,-1):
        if i<len(rows)-1 and (rows[i+1].timestamp-rows[i].timestamp).total_seconds()!=300:break
        tail+=1
    return {'category':category,'provider_status':getattr(result,'status','unknown'),'provider_issues':[x.code for x in getattr(result,"issues",[])],
        'saved_bars':len(rows),'first_bar_at':rows[0].timestamp.isoformat() if rows else None,
        'last_bar_at':rows[-1].timestamp.isoformat() if rows else None,
        'last_completed_bar_age_seconds':(now-rows[-1].timestamp).total_seconds()-300 if rows else None,
        'internal_gap_count':len(gaps),'missing_internal_intervals':sum(max(0,x//300-1) for x in gaps),
        'contiguous_tail_bars':tail,'quality_codes':codes,
        'interpretation':'IEX-only observed coverage; no-trade interval, halt, symbol mapping or provider loss not distinguished. Missing bars are not filled.'}


def summarize(manifest):
    checked=[r for r in manifest if r.get('chart_diagnostics')]
    return {'checked':len(checked),'categories':dict(Counter(r['chart_diagnostics']['category'] for r in checked)),
        'gapped_with_contiguous_last_20':sum(r['chart_diagnostics']['category']=='gapped_iex_history' and r['chart_diagnostics'].get('contiguous_tail_bars',0)>=20 for r in checked),
        'quality_gates_changed':False}
