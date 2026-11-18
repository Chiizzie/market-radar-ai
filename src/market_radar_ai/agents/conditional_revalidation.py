"""Refresh a reviewed fixed plan without re-running its initial signal search.

Initial relative volume is a selection fact. Invalidation is current price/risk,
changed news, revised historical bars, broken support, or expired evidence.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal as D
from .candidate_packages import canonical
from .setup_checks import validate_paper_plan


def revalidate(body, document, feed, *, now):
    from .qualification import qualify
    from .paper_verdict import stable_evidence
    from .chart_news import valid_check
    plan=deepcopy(body['plan']);blocks=[]
    try:
        rows=qualify(document,feed,now=now)['candidates']
        matches=[r for r in rows if r['candidate_id']==body['candidate_id']]
        if len(matches)!=1:return None,['fresh_setup_evidence_unavailable']
        row=matches[0];checks=row['reference_checks'];tech=row['technical_checks']
        for k in ('catalogue_candidate','market_session','reference_quote','fx'):
            if checks.get(k)!='PASS':blocks.append(k+'_not_confirmed')
        if tech.get('state')!='MEASURED':blocks.append('fresh_chart_unavailable')
        if tech.get('close_above_rolling_vwap') is not True:blocks.append('fresh_price_below_vwap')
        momentum=tech.get('momentum_window_pct',tech.get('momentum_20_bars_pct'))
        if momentum is None or D(momentum)<=0:blocks.append('fresh_momentum_nonpositive')
        old_strategy=body['technical_checks']['strategy_id']
        if old_strategy in ('trend_continuation_20bar_v1','trend_pullback_reclaim_v1'):
            if not valid_check(row.get('chart_news_check'),symbol=body['symbol'],now=now):
                blocks.append('chart_news_check_missing_or_incomplete')
        elif not row.get('current_news_source_ids'):blocks.append('current_symbol_linked_news_missing')
        # Changed article content or event dates requires a new assessment.
        kinds=('news:','calendar:')
        old_news={k:v for k,v in body['sources'].items() if k.startswith(kinds)}
        new_news={k:v for k,v in row['review_sources'].items() if k.startswith(kinds)}
        if stable_evidence(old_news)!=stable_evidence(new_news):blocks.append('material_news_or_calendar_changed')
        old_market=next(v for k,v in body['sources'].items() if k.startswith('market:'))
        new_market=next(v for k,v in row['review_sources'].items() if k.startswith('market:'))
        old_bars=old_market['candles'];new_bars=new_market['candles']
        def at(c):return datetime.fromisoformat(c['timestamp'].replace('Z','+00:00'))
        old_map={at(c):c for c in old_bars};new_map={at(c):c for c in new_bars}
        common=set(old_map)&set(new_map)
        if not common or any(canonical(old_map[t])!=canonical(new_map[t]) for t in common):
            blocks.append('historical_chart_changed')
        native_stop=D(plan['stop_eur'])/D(plan['fx_rate'])
        if any(D(c['low'])<=native_stop for c in new_bars if at(c)>max(old_map)):
            blocks.append('reviewed_support_broken')
        new_rate=D(row['conditional_paper_plan']['fx_rate']) if row.get('conditional_paper_plan') else None
        if plan['native_currency']=='EUR':new_rate=D(1)
        elif new_rate is None:
            from .candidate_packages import digest
            record=document['stock_reference_checks']
            if digest(record['payload'])!=record['payload_sha256']:raise ValueError('fx_integrity')
            new_rate=D(record['payload']['fx']['eur_per_unit'])
        if abs(new_rate/D(plan['fx_rate'])-1)*10000>D('10'):
            blocks.append('material_fx_change')
        ask,bid,entry,stop,qty,cost=[D(str(v)) for v in
            (checks['indicative_ask_eur'],checks['indicative_bid_eur'],plan['entry_eur'],
             plan['stop_eur'],plan['quantity'],plan['assumed_round_trip_cost_eur'])]
        if not all(v.is_finite() and v>0 for v in (ask,bid,entry,stop,qty)):raise ValueError('price_invalid')
        if bid>ask:blocks.append('reference_quote_crossed')
        if bid<=stop:blocks.append('setup_invalidated_before_entry')
        if (ask-bid)/((ask+bid)/2)*10000>D(20):blocks.append('reference_spread_exceeds_20bps')
        if (ask/entry-1)*10000>D(20):blocks.append('entry_gap_exceeds_20bps')
        if (max(ask,entry)-stop)*qty+cost>D(20):blocks.append('fresh_risk_exceeds_20eur')
        deadlines=[now+timedelta(seconds=180),datetime.fromisoformat(body['assembled_at'])+timedelta(seconds=360),
                   datetime.fromisoformat(plan['exit_by']),datetime.fromisoformat(checks['exit_deadline']),
                   max(new_map)+timedelta(seconds=900)]
        if checks.get('reference_expires_at'):deadlines.append(datetime.fromisoformat(checks['reference_expires_at']))
        plan['expires_at']=min(deadlines).isoformat()
        blocks.extend(validate_paper_plan(plan,now=now,exit_deadline=checks['exit_deadline'])['failures'])
        return (plan if not blocks else None),sorted(set(blocks))
    except (ValueError,TypeError,KeyError,StopIteration,ArithmeticError):
        return None,sorted(set(blocks+['fresh_revalidation_incomplete']))
