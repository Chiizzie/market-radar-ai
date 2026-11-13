"""Fictional fixtures; no test rows enter forward journals or historical libraries."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from decimal import Decimal as D
import gzip
import json
from pathlib import Path

import pytest
from test_method_shadow import fixture as method_fixture, NOW as METHOD_NOW
from test_competitor_shadow import inputs as competitor_fixture
from test_pullback_strategy import synthetic_setup
from test_knowledge_retrieval import library as base_library
from market_radar_ai.agents.candidate_packages import canonical, digest
from market_radar_ai.agents.chart_news import checked_source
from market_radar_ai.agents.strategy_registry import route, evaluate, baseline_strategy, ALL, CORE, OFFLINE, METHODS, source_protocol
from market_radar_ai.agents.strategy_knowledge import imported_v1, seal, validate, Retriever, compact_features, playbook, CUTOFF
from market_radar_ai.agents.strategy_pair import prepare, run, validate as validate_pair
from market_radar_ai.agents.strategy_routing_live import evaluate_batch, permitted
from market_radar_ai.agents.mean_reversion import measure, scenario
from market_radar_ai.agents.paper_comparison import aware


def shifted(value, days=10):
    if isinstance(value,dict):return {k:shifted(v,days) for k,v in value.items()}
    if isinstance(value,list):return [shifted(v,days) for v in value]
    if isinstance(value,str) and value.startswith('2026-') and 'T' in value:
        try:return (aware(value)+timedelta(days=days)).isoformat()
        except ValueError:pass
    return value


def rehash(source):
    source['reference_checks']['payload_sha256']=digest(source['reference_checks']['payload'])
    return source


def method_input():
    source=rehash(shifted(method_fixture()));now=METHOD_NOW+timedelta(days=10)
    return source,now


def pullback_input():
    doc,feed,now=synthetic_setup();s=method_fixture()
    s.update(candles=doc['captures'][0]['payload']['candles'],bars_received_at=now.isoformat(),
        reference_checks=doc['stock_reference_checks'],news_check=checked_source(feed,symbol='TEST',now=now),news_input=None)
    s['context']['retrieved_at']=now.isoformat()
    return rehash(shifted(s)),now+timedelta(days=10)


def opening_input():
    source=method_fixture();now=METHOD_NOW.replace(hour=14,minute=45,second=1)
    source['candles']=source['candles'][:3]
    for c in source['candles']:
        c['volume']='20000';c['high']='100';c['low']='98';c['open']='99.6';c['close']='99.9'
    refresh(source,now,99.98,100)
    return rehash(shifted(source)),now+timedelta(days=10)


def refresh(s,now,bid,ask):
    s['bars_received_at']=s['context']['retrieved_at']=s['news_check']['checked_at']=now.isoformat()
    p=s['reference_checks']['payload'];p['retrieved_at']=p['market_clock']['timestamp']=p['fx']['observed_at']=now.isoformat()
    p['quotes']['quotes'][s['symbol']].update(t=now.isoformat(),bp=bid,ap=ask)
    rehash(s)


def mean_input():
    s=method_fixture();now=METHOD_NOW.replace(hour=16,minute=20,second=1);start=now.replace(hour=14,minute=30,second=0)
    bars=[]
    for j,price in enumerate([D('99.5'),D('100.5')]*10+[D(97),D('97.2')]):
        bars.append({'symbol':'TEST','source':'alpaca_iex','interval':'5m','quote_currency':'USD',
            'timestamp':(start+timedelta(minutes=5*j)).isoformat(),'open':str(price-D('.05')),
            'high':str(price+D('.1') if j<20 else D('97.1') if j==20 else D('97.25')),
            'low':str(price-D('.1') if j<20 else D('96.8') if j==20 else D('97.05')),
            'close':str(price),'volume':'20000'})
    s['candles']=bars;refresh(s,now,97.23,97.25)
    return rehash(shifted(s)),now+timedelta(days=10)


def knowledge():
    base=base_library()
    return seal(imported_v1(base),base_library_id=base['library_id'],built_at='2026-11-13T22:10:00+00:00',manifests=[])


def test_independent_variants_retain_pullback_and_continuation_without_mutation():
    source,now=pullback_input();original=deepcopy(source);rows=route(source,now=now)
    assert len(rows)==6 and len({r['strategy_id'] for r in rows})==6
    eligible={r['strategy_id'] for r in rows if r['eligible']}
    assert {'trend_pullback_reclaim_v1','trend_continuation_20bar_v1'}<=eligible,rows
    assert source==original and baseline_strategy(source,now=now)=='trend_pullback_reclaim_v1'
    plans=[r['plan'] for r in rows if r['eligible']]
    assert plans[0] is not plans[1]
    assert all(D(p['planned_loss_eur'])<=20 for p in plans)
    assert len({r['result_id'] for r in rows})==6


@pytest.mark.parametrize('make,strategy',[(method_input,'session_open_avwap_reclaim_v1'),
    (opening_input,'opening_range_15m_shadow_v1')])
def test_existing_methods_produce_independent_cost_inclusive_plans(make,strategy):
    s,now=make();r=evaluate(s,strategy,now=now)
    assert r['eligible'],r
    p=r['plan'];assert D(p['entry_eur'])*D(p['quantity'])+D(p['assumed_round_trip_cost_eur'])<=500
    assert D(p['planned_loss_eur'])<=20 and r['trade_authorized'] is False


def test_competitor_route_requires_actual_named_relationship_and_post_news_response():
    s=rehash(shifted(competitor_fixture()));now=METHOD_NOW+timedelta(days=10)
    r=evaluate(s,'competitor_strength_breakout_shadow_v1',now=now);assert r['eligible'],r
    s['competitor_evidence']['links'][0]['headline']='Unrelated news'
    r=evaluate(s,'competitor_strength_breakout_shadow_v1',now=now)
    assert not r['eligible'] and 'post_news_competitor_strength_unconfirmed' in r['blockers']


@pytest.mark.parametrize('fault',['hash','wide','stale','future','symbol','gap','fx','risk_time'])
def test_bad_common_inputs_never_create_core_alternatives(fault):
    s,now=pullback_input();p=s['reference_checks']['payload'];q=p['quotes']['quotes']['TEST']
    if fault=='hash':s['reference_checks']['payload_sha256']='0'*64
    if fault=='wide':q['bp']=q['ap']*.98
    if fault=='stale':q['t']=(now-timedelta(seconds=61)).isoformat()
    if fault=='future':s['candles'][-1]['timestamp']=now.isoformat()
    if fault=='symbol':s['candles'][0]['symbol']='OTHER'
    if fault=='gap':s['candles'][4]['timestamp']=s['candles'][3]['timestamp']
    if fault=='fx':p['fx']['observed_at']=(now-timedelta(hours=1)).isoformat()
    if fault=='risk_time':now=now.replace(hour=22)
    if fault!='hash':rehash(s)
    rows=route(s,now=now)
    assert not any(r['eligible'] for r in rows if r['strategy_id'] in CORE)


def test_mean_reversion_uses_pre_signal_baseline_and_stays_offline():
    s,now=mean_input();m=measure(s['candles'],s['daily'],symbol='TEST',now=now)
    assert not m['blockers'],m
    assert D(m['features']['baseline_mean_native'])==100
    assert aware(m['features']['baseline_last_bar_at'])==aware(s['candles'][-3]['timestamp'])
    r=evaluate(s,OFFLINE,now=now);assert r['eligible'],r
    assert r['offline_only'] and OFFLINE not in {x['strategy_id'] for x in route(s,now=now)}
    changed=deepcopy(s);changed['candles'][-1]['close']='97.21'
    assert measure(changed['candles'],changed['daily'],symbol='TEST',now=now)['features']['baseline_mean_native']=='100.0'
    with pytest.raises(ValueError,match='offline'):prepare(r,s,Retriever(knowledge()),now=now)


@pytest.mark.parametrize('fault',['trend','no_recovery','gap','future','low_volume','no_target'])
def test_mean_reversion_rejects_incompatible_regime_or_evidence(fault):
    s,now=mean_input()
    if fault=='trend':
        for j,c in enumerate(s['candles'][:20]):c.update(open=str(99+j/20),close=str(99+j/20),high=str(99.1+j/20),low=str(98.9+j/20))
    if fault=='no_recovery':s['candles'][-1]['open']='97.3'
    if fault=='gap':s['candles'][2]['timestamp']=s['candles'][1]['timestamp']
    if fault=='future':s['candles'][-1]['timestamp']=now.isoformat()
    if fault=='low_volume':
        for c in s['candles']:c['volume']='1'
    if fault=='no_target':s['candles'][-1]['high']='101'
    r=evaluate(s,OFFLINE,now=now);assert not r['eligible'],r


def test_expanded_playbooks_preserve_source_policy_and_partition_history():
    lib=knowledge();s,now=pullback_input();rows=route(s,now=now);retriever=Retriever(lib)
    assert len({playbook(x)['source_id'] for x in ALL})==7
    for r in rows:
        context=retriever.retrieve(r,s,as_of=now)
        assert all(c['strategy_id']==r['strategy_id'] and c['source_protocol_id']==r['source_protocol_id'] for c in context['cases'])
    method=evaluate(*method_input()[:1], 'session_open_avwap_reclaim_v1',now=method_input()[1])
    assert 'not_v2_guarded' in playbook(method['strategy_id'])['historical_source_policy']


def test_baseline_and_knowledge_pair_same_inputs_without_sharing_verdicts():
    s,now=pullback_input();r=evaluate(s,'trend_pullback_reclaim_v1',now=now);retriever=Retriever(knowledge())
    pair=prepare(r,s,retriever,now=now);before=deepcopy(pair)
    assert pair['arms']['baseline']=={k:v for k,v in pair['arms']['knowledge'].items() if k!='reference_knowledge'}
    def ask(arm,prompt,schema,key):
        assert prompt['peer_reviews']==[]
        sid=prompt['packet']['source_ids'][0];prompt['packet']['plan']['stop_eur']='0'
        return {'data':{'verdict':'MORE_EVIDENCE_REQUIRED','rationale':'Fictional fixture','source_ids':[sid],'concerns':[]},'usage':{'synthetic':True}}
    report=run(pair,retriever,ask=ask,clock=lambda:now)
    assert report['state']=='complete' and pair==before and not report['trade_authorized']
    pair['result']['plan']['stop_eur']='0'
    with pytest.raises(ValueError):validate_pair(pair,retriever,now=now)


def test_overlap_is_reported_without_summing_alternative_positions_or_profit():
    s,now=pullback_input();report=evaluate_batch([s],knowledge(),now=now)
    assert report['strategy_evaluations']==6 and report['additional_eligible_core_setups']>=1
    assert report['overlap_groups'][0]['alternative_plans_not_additive_positions'] is True
    assert report['performance_claim'] is None and report['model_calls']==0
    with pytest.raises(ValueError):evaluate_batch([s,s],knowledge(),now=now)


def test_late_response_or_historical_only_approval_cannot_complete_pair():
    s,now=pullback_input();r=evaluate(s,'trend_pullback_reclaim_v1',now=now);retriever=Retriever(knowledge());pair=prepare(r,s,retriever,now=now)
    current=[now]
    def ask(*args):
        current[0]+=timedelta(minutes=5)
        return {'data':{'verdict':'APPROVE_PAPER','rationale':'Late fiction','source_ids':[pair['arms']['baseline']['packet']['source_ids'][0]],'concerns':[]},'usage':{'settled_microeur':42}}
    report=run(pair,retriever,ask=ask,clock=lambda:current[0])
    assert report['state']=='incomplete' and report['model_calls']==1
    assert next(iter(report['arms'].values()))['usage']['settled_microeur']==42


def test_period_and_session_gates_precede_all_provider_calls():
    assert not permitted(aware('2026-11-13T15:00:00Z'))
    assert not permitted(aware('2026-11-14T15:00:00Z'))
    assert not permitted(aware('2026-11-16T22:00:00Z'))
    assert permitted(aware('2026-11-16T15:00:00Z'))


def opening_continuation_input():
    from market_radar_ai.evidence.news import parse_news
    from market_radar_ai.agents.news_input import build_news_input
    s=method_fixture();now=METHOD_NOW.replace(hour=15,minute=0,second=1);s['candles']=s['candles'][:6]
    for j,c in enumerate(s['candles']):
        price=D('99.4')+D(j)*D('.1')
        c.update(open=str(price-D('.05')),close=str(price),high=str(price+D('.05')) if j else '100.1',low=str(price-D('.1')),volume='10000' if j<3 else '25000')
    refresh(s,now,99.98,100)
    s=rehash(shifted(s));now+=timedelta(days=10)
    news=parse_news({'feed':[{'title':'Fictional company update','source':'Fixture Publisher','url':'https://example.com/fixture',
        'time_published':(now-timedelta(minutes=10)).strftime('%Y%m%dT%H%M%S'),'ticker_sentiment':[{'ticker':'TEST'}]}]},now=now)
    s['news_input']=build_news_input(news,symbol='TEST',now=now).model_dump(mode='json')
    return s,now


def test_original_opening_continuation_is_independent_and_still_needs_news():
    s,now=opening_continuation_input();r=evaluate(s,'opening_continuation_30m_v1',now=now)
    assert r['eligible'],r
    assert not evaluate(s,'trend_continuation_20bar_v1',now=now)['eligible']
    s['news_input']=None
    assert 'current_symbol_linked_news_missing' in evaluate(s,'opening_continuation_30m_v1',now=now)['blockers']


def test_history_import_preserves_original_case_outcomes_and_policy_without_relabelling():
    from test_knowledge_retrieval import case
    base=base_library([case(1,'closed','-12.34'),case(2,'unresolved'),case(3,'not_filled')])
    original=deepcopy(base);rows=imported_v1(base)
    assert base==original
    assert sorted(c['code_only']['state'] for c in rows)==['closed','not_filled','unresolved']
    assert next(c for c in rows if c['code_only']['state']=='closed')['code_only']['net_pnl_eur']=='-12.34'
    lib=seal(rows,base_library_id=base['library_id'],built_at='2026-11-13T22:10:00Z',manifests=[])
    lib['cases'][0]['source_policy']='fake_policy';lib['library_id']=digest({k:v for k,v in lib.items() if k!='library_id'})
    with pytest.raises(ValueError,match='invalid_strategy_case'):validate(lib)


def test_method_journal_cutoff_requires_server_receipt_and_exact_original_scenario(tmp_path):
    from market_radar_ai.agents.strategy_knowledge_build import replay
    from market_radar_ai.agents.method_scenarios import scenario as old_scenario
    from market_radar_ai.agents.comparison_live import envelope, event_id
    s=rehash(shifted(method_fixture(),6));now=METHOD_NOW+timedelta(days=6)
    scenario=old_scenario(s,now=now);strategy='session_open_avwap_reclaim_v1';pid=source_protocol(strategy)
    raw=envelope('method_enrol',{'setup_id':scenario['setup_id'],'protocol_id':pid,'shadow_only':True,'scenario':scenario,'inputs':s},now)
    e={**raw,'seq':1,'experiment_id':pid,'day':'2026-11-12','received_at':now.isoformat(),'event_id':event_id(pid,raw)}
    path=tmp_path/'source.gz'
    with gzip.open(path,'wt') as f:f.write(canonical(e)+'\n')
    rows,m=replay(path,strategy=strategy,day='2026-11-12')
    assert len(rows)==1 and rows[0]['code_only']['state']=='not_filled'
    assert rows[0]['code_only']['net_pnl_eur'] is None and 'not_v2_guarded' in rows[0]['source_policy']
    e['received_at']='2026-11-16T15:00:00Z'
    with gzip.open(path,'wt') as f:f.write(canonical(e)+'\n')
    rows,m=replay(path,strategy=strategy,day='2026-11-12')
    assert not rows and m['after_cutoff_excluded']==1
    e['received_at']=now.isoformat();e['payload_json']='{}'
    with gzip.open(path,'wt') as f:f.write(canonical(e)+'\n')
    with pytest.raises(ValueError):replay(path,strategy=strategy,day='2026-11-12')


def test_future_library_and_outcome_changes_cannot_change_case_selection():
    from test_knowledge_retrieval import case
    base=base_library([case(i,'closed',str(i)) for i in range(1,9)])
    rows=imported_v1(base);lib=seal(rows,base_library_id=base['library_id'],built_at='2026-11-13T22:10:00Z',manifests=[])
    s,now=pullback_input();result=evaluate(s,'trend_pullback_reclaim_v1',now=now)
    a=Retriever(lib).retrieve(result,s,as_of=now)
    for c in rows:c['code_only']['net_pnl_eur']=str(-D(c['code_only']['net_pnl_eur'])*100)
    other=seal(rows,base_library_id=base['library_id'],built_at=lib['built_at'],manifests=[])
    b=Retriever(other).retrieve(result,s,as_of=now)
    assert [c['case_id'] for c in a['cases']]==[c['case_id'] for c in b['cases']]
    future=seal(rows,base_library_id=base['library_id'],built_at='2026-11-17T00:00:00Z',manifests=[])
    with pytest.raises(ValueError,match='unavailable'):Retriever(future).retrieve(result,s,as_of=now)
