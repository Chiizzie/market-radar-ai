"""Independent, reproducible research routes. The production winner is unchanged."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D, ROUND_DOWN

from .candidate_packages import digest, canonical
from .candidate_plan import draft
from .combined_input import MarketEvidence
from .knowledge_playbooks import RULES as CORE_RULES
from .knowledge_cases import features as core_features
from .paper_comparison import aware, GUARDED_PROTOCOL
from .paper_verdict import paper_gate
from .setup_checks import reference_checks, technical_checks, validate_paper_plan
from .news_input import NewsResearchInput
from .method_scenarios import scenario as avwap_scenario, PROTOCOL as AVWAP_PROTOCOL
from .early_opening import scenario as opening_scenario, PROTOCOL as OPENING_PROTOCOL
from .competitor_shadow import scenario as competitor_scenario, PROTOCOL as COMPETITOR_PROTOCOL
from .mean_reversion import scenario as reversion_scenario, PROTOCOL as REVERSION_PROTOCOL

CORE = tuple(sorted(CORE_RULES))
METHODS = {p['rules']['strategy_id']:(fn,p) for fn,p in (
    (avwap_scenario,AVWAP_PROTOCOL),(opening_scenario,OPENING_PROTOCOL),(competitor_scenario,COMPETITOR_PROTOCOL))}
OFFLINE = REVERSION_PROTOCOL['rules']['strategy_id']
ALL = CORE + tuple(sorted(METHODS)) + (OFFLINE,)
PROTOCOL = {'version':'independent-strategy-routing-v2','validation_start':'2026-11-16T00:00:00+00:00',
    'core_source':'208f4bf5f9f1f403fb977075f0ea33912f4463b0',
    'method_source':'889f1a110f9f7ac9d88dbbbc7e9548e8fe00f2c5',
    'core_strategies':CORE,'methods':{s:digest(p) for s,(_,p) in METHODS.items()},
    'offline_only':{OFFLINE:digest(REVERSION_PROTOCOL)},
    'selection':'Evaluate every strategy independently on identical symbol inputs; no winner overwrite.',
    'allocation':'Alternative plans overlap; normalize quantity downward to cost-inclusive EUR500; never add alternatives as independent positions.',
    'maximum_reference_spread_bps':'20','maximum_planned_loss_eur':'20','no_ai':True,'no_alerts':True}
PROTOCOL_ID = digest(PROTOCOL)


def source_protocol(strategy):
    return digest(GUARDED_PROTOCOL) if strategy in CORE else digest(REVERSION_PROTOCOL if strategy==OFFLINE else METHODS[strategy][1])


def source_policy(strategy):
    return ('guarded_reference_quotes_v2' if strategy in CORE else 'offline_no_forward_outcomes' if strategy==OFFLINE
            else 'legacy_method_entry_guards_exit_quotes_not_v2_guarded')


def _core(inputs, strategy, now):
    raw=inputs['candles'][-60:]
    bars=MarketEvidence(symbol=inputs['symbol'],provider='alpaca_iex',retrieved_at=inputs['bars_received_at'],
        validated_at=now,original_capture_sha256=digest(raw),quote_currency='USD',candles=raw)
    checks=reference_checks({'stock_reference_checks':inputs['reference_checks']},symbol=inputs['symbol'],market='stocks',now=now)
    fx=inputs['reference_checks']['payload'].get('fx')
    tech=technical_checks(bars,market='stocks',strategy_id=strategy)
    plan=draft(bars,fx,now=now,market='stocks',strategy_id=strategy)
    if plan and checks.get('exit_deadline'):
        plan['exit_by']=checks['exit_deadline']
        plan['expires_at']=min(aware(plan['expires_at']),aware(plan['exit_by'])).isoformat()
    news_ids=[]
    if inputs.get('news_input'):
        news=NewsResearchInput.model_validate(inputs['news_input'])
        if news.symbol!=inputs['symbol'] or aware(news.assembled_at)>now or (now-news.assembled_at).total_seconds()>60:
            raise ValueError('news_identity_or_age')
        news_ids=[x.source_id for x in news.evidence if 0 <= (now-x.published_at).total_seconds() <= 3600 and 0 <= (now-x.retrieved_at).total_seconds() <= 900]
    row={'market':'stocks','symbol':inputs['symbol'],'reference_checks':checks,'technical_checks':tech,
         'conditional_paper_plan':plan,'chart_news_check':inputs.get('news_check'),'current_news_source_ids':news_ids}
    gate=paper_gate(row,now=now)
    result={'features':tech,'blockers':gate['paper_blockers'],'plan':plan if gate['eligible_for_paper_review'] else None}
    return result


def evaluate(inputs, strategy, *, now):
    now=aware(now)
    if strategy not in ALL: raise ValueError('unknown_strategy')
    source=deepcopy(inputs); original=digest(source)
    row={'schema_version':'independent-strategy-result-v2','routing_protocol_id':PROTOCOL_ID,
        'strategy_id':strategy,'source_protocol_id':source_protocol(strategy),'source_policy':source_policy(strategy),
        'candidate_id':'stocks:'+source['symbol'],'assembled_at':now.isoformat(),'input_sha256':original,
        'offline_only':strategy==OFFLINE,'features':{},'plan':None,'blockers':[],'eligible':False,
        'model_calls':0,'trade_authorized':False}
    try:
        if len(canonical(source).encode())>180000: raise ValueError('source_capacity')
        # Common quote/risk checks supplement, never replace, the original detector.
        check=source['reference_checks']; payload=check['payload']
        if digest(payload)!=check['payload_sha256']: raise ValueError('reference_hash')
        result=(_core(source,strategy,now) if strategy in CORE else
                (reversion_scenario if strategy==OFFLINE else METHODS[strategy][0])(source,now=now))
        row.update(features=result['features'],plan=result['plan'],blockers=list(result['blockers']))
        refs=reference_checks({'stock_reference_checks':check},symbol=source['symbol'],market='stocks',now=now)
        if refs.get('reference_quote')!='PASS': row['blockers'].append('current_reference_quote_missing')
        bid,ask=D(str(refs.get('indicative_bid_eur'))),D(str(refs.get('indicative_ask_eur')))
        if not bid.is_finite() or not ask.is_finite() or not 0<bid<=ask: raise ValueError('quote_values')
        if (ask-bid)/((ask+bid)/2)*10000>D(20): row['blockers'].append('reference_spread_exceeds_20bps')
        if row['plan'] and not row['blockers']:
            p=row['plan'];entry,stop,qty,cost=[D(p[k]) for k in ('entry_eur','stop_eur','quantity','assumed_round_trip_cost_eur')]
            unit_cost=cost/qty
            qty=min(qty,D(500)/(entry+unit_cost)).quantize(D('.000001'),rounding=ROUND_DOWN)
            cost=unit_cost*qty
            normalized={**p,'quantity':str(qty),'assumed_round_trip_cost_eur':str(cost),
                        'paper_capital_eur':'500','planned_loss_eur':str((entry-stop)*qty+cost),'trade_authorized':False}
            risk=validate_paper_plan(normalized,now=now,exit_deadline=refs.get('exit_deadline'))
            row['blockers'].extend(risk['failures']); row['plan']=normalized
        row['blockers']=sorted(set(row['blockers']))
        row['eligible']=not row['blockers'] and row['plan'] is not None
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):
        row.update(plan=None,eligible=False,blockers=['strategy_inputs_invalid_or_missing'])
    if digest(source)!=original: raise ValueError('strategy_mutated_source')
    if not row['eligible']: row['plan']=None
    row['result_id']=digest(row)
    return row


def route(inputs, *, now, include_offline=False):
    selected=ALL if include_offline else tuple(s for s in ALL if s!=OFFLINE)
    rows=[evaluate(inputs,s,now=now) for s in selected]
    assert len({r['strategy_id'] for r in rows})==len(selected)
    return rows


def validate_result(result, inputs, *, now):
    built=evaluate(inputs,result['strategy_id'],now=aware(result['assembled_at']))
    if result!=built: raise ValueError('strategy_result_not_reproducible')
    current=evaluate(inputs,result['strategy_id'],now=now)
    if not current['eligible'] or not result['eligible']: raise ValueError('strategy_no_longer_eligible')
    return current


def baseline_strategy(inputs, *, now):
    """Original single-label selection, for same-input coverage diagnostics only."""
    try:
        rows=inputs['candles'][-60:]
        bars=MarketEvidence(symbol=inputs['symbol'],provider='alpaca_iex',retrieved_at=inputs['bars_received_at'],
            validated_at=aware(now),original_capture_sha256=digest(rows),quote_currency='USD',candles=rows)
        return technical_checks(bars,market='stocks').get('strategy_id')
    except (ValueError,TypeError,KeyError,AttributeError):return None
