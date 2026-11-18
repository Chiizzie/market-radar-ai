from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from test_stock_context import document, context, NOW
from test_candidate_review import answer
from test_scheduled_review import Store, ENV
from market_radar_ai.agents.session_briefing import build_briefing, briefing_slot
from market_radar_ai.agents.candidate_packages import digest, canonical
from market_radar_ai.agents.candidate_review import run, STAGES
from market_radar_ai.agents.scheduled_review import execute, claim_review, decision_summary
from market_radar_ai.dashboard.candidate_delivery import export_archive


def universe(no_intraday=False):
    def mutate(frame,data):
        if no_intraday and frame=='5Min':data['bars']=[]
    d=document(context(mutation=mutate))
    other=deepcopy(d['stock_context'][0]);p=other['payload'];p['symbol']='AAPL'
    for section in ('daily','intraday'):
        for row in p[section]['bars']:row['symbol']='AAPL'
    other['payload_sha256']=digest(p)
    d['captures'].append({'market':'stocks','requested_symbol':'AAPL'})
    d['stock_context'].append(other)
    d['captures'].append({'market':'stocks','requested_symbol':'AMD'})
    return d


def session_answer(stage,p,s):
    out=answer(stage,p,s)
    out['symbol_decisions']=[dict(symbol=symbol,posture='WATCHLIST',rationale='Prior session levels are context.',
        opening_condition='Wait for fresh opening evidence.',invalidation='Stand aside if conditions fail.',
        source_ids=[p['snapshot']['symbol_evidence'][symbol]['source_ids'][0]]) for symbol in p['snapshot']['covered_symbols']]
    return out


def bundle(no_intraday=False):
    d=universe(no_intraday); record=build_briefing(d,None,now=NOW)['packages'][0]
    result=run(record,d,None,session_answer,clock=lambda:NOW)
    audit=dict(schema_version='paid-session-briefing-v1',state='completed',trade_authorized=False,
        result=result,calls=[dict(stage=r['stage'],state='received',estimated_cost_microeur=1,untrusted_response=r) for r in result['reviews']])
    return record,d,None,audit

@pytest.mark.parametrize('date,slot',[
    ('2026-11-04T07:59:59+00:00',None),('2026-11-04T08:00:00+00:00','morning'),
    ('2026-11-04T13:29:59+00:00','morning'),('2026-11-04T13:30:00+00:00','preopen'),
    ('2026-11-04T14:29:59+00:00','preopen'),('2026-11-04T14:30:00+00:00','opening'),
    ('2026-11-04T15:00:00+00:00','intraday'),('2026-11-07T09:00:00+00:00',None),
    ('2026-03-16T12:30:00+00:00','preopen'),('2026-03-16T13:30:00+00:00','opening'),
    ('2026-07-06T07:00:00+00:00','morning')])
def test_morning_preopen_opening_and_dst(date,slot):
    assert briefing_slot(datetime.fromisoformat(date))==slot

@pytest.mark.parametrize('no_intraday',[False,True])
def test_entire_universe_with_zero_or_one_current_bar(no_intraday):
    record,d,feed,audit=bundle(no_intraday)
    p=record['package']
    assert p['covered_symbols']==['AAPL','MSFT'] and p['unavailable_symbols']==['AMD']
    assert p['candidate_id']=='stocks:MARKET_OVERVIEW'
    assert all(s['intraday_bar_count']<=1 for k,s in p['sources'].items() if k.startswith('context:'))
    assert audit['result']['evidence_status']=='CURRENT_CONTEXT_ONLY'
    archive=export_archive(record,d,feed,audit)
    assert archive['schema_version']=='session-briefing-archive-v1' and archive['plan'] is None
    summary=decision_summary(record,d,feed,audit)
    assert 'review_evidence_expired' not in summary['blockers']
    assert len(summary['symbol_decisions'])==2 and summary['final_decision']=='NO_ACTION'

def test_independence_and_debate_sees_per_symbol_decisions():
    d=universe();r=build_briefing(d,None,now=NOW)['packages'][0];seen=[]
    def ask(stage,p,s):
        if stage in ('debate','conclusion'):
            assert all('symbol_decisions' in peer for peer in p['peer_reviews'])
            assert len(p['peer_reviews'])==len(seen)
        else:assert p['peer_reviews']==[]
        seen.append(stage);return session_answer(stage,p,s)
    run(r,d,None,ask,clock=lambda:NOW)
    assert seen==STAGES

@pytest.mark.parametrize('fault',['omit','duplicate','wrong_source'])
def test_no_omitted_stocks_or_cross_symbol_citations(fault):
    d=universe();r=build_briefing(d,None,now=NOW)['packages'][0]
    def ask(stage,p,s):
        out=session_answer(stage,p,s)
        if fault=='omit':out['symbol_decisions'].pop()
        if fault=='duplicate':out['symbol_decisions'][1]=out['symbol_decisions'][0]
        if fault=='wrong_source':out['symbol_decisions'][1]['source_ids']=out['symbol_decisions'][0]['source_ids']
        return out
    with pytest.raises(ValueError):run(r,d,None,ask,clock=lambda:NOW)

def test_changed_historical_level_fails_reproduction():
    d=universe();r=build_briefing(d,None,now=NOW)['packages'][0]
    next(iter(r['package']['sources'].values()))['prior_session']['close']='999'
    r['package_id']=digest(r['package'])
    with pytest.raises(ValueError,match='context_checksum_mismatch'):run(r,d,None,session_answer,clock=lambda:NOW)

def test_each_phase_has_own_durable_quota_not_consuming_stock_plan():
    s=Store()
    for phase in ('stocks_morning','stocks_preopen','stocks_opening','stocks'):
        assert claim_review(s,phase,NOW)
        assert not claim_review(s,phase,NOW)

def test_scheduler_does_not_buy_preopen_context_reviews(tmp_path,monkeypatch):
    import market_radar_ai.agents.scheduled_review as m
    s=Store();calls=[];d=universe(no_intraday=True)
    monkeypatch.setattr(m,'build_packages',lambda *a,**k:{'packages':[]})
    monkeypatch.setattr(m,'GitHubBudgetStore',lambda _:s)
    monkeypatch.setattr(m,'OpenAIPilot',lambda **k:object())
    fx=SimpleNamespace(eur_per_unit='0.9',model_dump=lambda **k:{'rate':'0.9'})
    monkeypatch.setattr(m,'YahooFxProvider',lambda:SimpleNamespace(fetch=lambda *a,**k:fx))
    def paid(client,record,capture,feed,**kw):
        calls.append(record['package']['covered_symbols'])
        result=run(record,capture,feed,session_answer,clock=kw['clock'])
        return dict(schema_version='paid-session-briefing-v1',state='completed',trade_authorized=False,
            result=result,calls=[dict(stage=r['stage'],state='received',estimated_cost_microeur=1,untrusted_response=r) for r in result['reviews']])
    monkeypatch.setattr(m,'run_paid',paid)
    monkeypatch.setattr(m,'deliver',lambda *a,**k:{'state':'candidate_archive_delivery_confirmed'})
    r=execute(d,None,tmp_path/'one',env={**ENV,'OPENAI_API_KEY':'test','GH_BUDGET_TOKEN':'test'},clock=lambda:NOW)
    assert r['state']=='no_qualified_candidate_zero_cost' and calls==[]
    r=execute(d,None,tmp_path/'two',env={**ENV,'OPENAI_API_KEY':'test','GH_BUDGET_TOKEN':'test'},clock=lambda:NOW)
    assert r['state']=='no_qualified_candidate_zero_cost' and calls==[] and s.version==0


def test_intraday_recovery_quota_is_single_and_preserves_opening():
    s=Store()
    assert claim_review(s,'stocks_opening',NOW)
    assert claim_review(s,'stocks_intraday',NOW)
    assert not claim_review(s,'stocks_intraday',NOW)
    assert not claim_review(s,'stocks_opening',NOW)


def test_recovery_refuses_any_model_reservation_or_uncertain_opening():
    from market_radar_ai.agents.scheduled_review import opening_recovery_allowed, PREFIX
    s=Store();day='2026-11-04'
    assert not opening_recovery_allowed(s.state,day)
    assert claim_review(s,'stocks_opening',NOW)
    assert opening_recovery_allowed(s.state,day)
    s.state['entries']['session-review-v1:package:stage']={'day':day,'reserved':100,'actual':None,'usage':None}
    assert not opening_recovery_allowed(s.state,day)
    s.state['entries']['session-review-v1:package:stage']['actual']=0
    assert not opening_recovery_allowed(s.state,day)
    del s.state['entries']['session-review-v1:package:stage']
    s.state['entries'][PREFIX+day+':stocks_opening']['actual']=None
    assert not opening_recovery_allowed(s.state,day)


def test_compact_decisions_roundtrip_without_losing_citations():
    from market_radar_ai.agents.candidate_review import compact_decisions
    r,d,f,a=bundle()
    original=a['result']['reviews'][0]['symbol_decisions']
    compact=compact_decisions(original)
    assert [dict(zip(compact['columns'],row)) for row in compact['rows']]==original


def test_oversized_session_is_rejected_before_any_agent_call(monkeypatch):
    import market_radar_ai.agents.candidate_review as m
    d=universe();r=build_briefing(d,None,now=NOW)['packages'][0]
    monkeypatch.setattr(m,'SESSION_PROMPT_BYTES',100)
    calls=[]
    with pytest.raises(ValueError,match='before_generation'):
        m.run(r,d,None,lambda *a:calls.append(a),clock=lambda:NOW)
    assert calls==[]


def reference_bundle():
    from test_stock_checks import payload
    d=universe();p=payload()
    p['symbols']=['AAPL','MSFT'];p['retrieved_at']=NOW.isoformat()
    p['market_clock']['timestamp']=NOW.isoformat()
    p['market_clock']['next_open']=(NOW+timedelta(days=1)).isoformat()
    p['market_clock']['next_close']=(NOW+timedelta(hours=5)).isoformat()
    p['fx']['observed_at']=NOW.isoformat()
    q=p['quotes']['quotes'].pop('IBM');q['t']=NOW.isoformat()
    p['quotes']['quotes']={s:deepcopy(q) for s in p['symbols']}
    p['catalogue_candidates']={s:[] for s in p['symbols']}
    d['stock_reference_checks']={'payload':p,'payload_sha256':digest(p)}
    record=build_briefing(d,None,now=NOW)['packages'][0]
    result=run(record,d,None,session_answer,clock=lambda:NOW)
    audit=dict(schema_version='paid-session-briefing-v1',state='completed',trade_authorized=False,
        result=result,calls=[dict(stage=r['stage'],state='received',estimated_cost_microeur=1,untrusted_response=r) for r in result['reviews']])
    return record,d,None,audit


def test_reference_checks_reach_reproducible_paid_archive_without_admission():
    record,d,feed,audit=reference_bundle()
    p=record['package']
    assert p['eur_conversion']=='indicative_reference_only'
    assert 'fresh_fx_conversion_missing' not in p['missing_evidence']
    assert 'broker_account_eligibility_unverified' in p['missing_evidence']
    for source in p['sources'].values():
        if source.get('schema_version')=='stock-session-summary-v1':
            assert source['reference_checks']['symbol']==source['symbol']
            assert source['reference_checks']['indicative_bid_eur']=='90.0'
    assert export_archive(record,d,feed,audit)['trade_authorized'] is False


def test_stale_checks_do_not_clear_fx_or_enter_briefing():
    record,d,feed,audit=reference_bundle()
    p=d['stock_reference_checks']['payload'];p['retrieved_at']=(NOW-timedelta(seconds=61)).isoformat()
    d['stock_reference_checks']['payload_sha256']=digest(p)
    rebuilt=build_briefing(d,feed,now=NOW)['packages'][0]['package']
    assert rebuilt['eur_conversion']=='not_supplied'
    assert all('reference_checks' not in s for s in rebuilt['sources'].values())
