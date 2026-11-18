from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest
from market_radar_ai.agents.paper_verdict import build_packets, review, finalize, paper_gate, STAGES
from market_radar_ai.agents.candidate_packages import digest
from test_setup_checks import plan_and_bars, NOW


def qualified_row():
    plan,_=plan_and_bars();plan['symbol']='TEST'
    quote=str((Decimal(plan['stop_eur'])+Decimal(plan['entry_eur']))/2)
    return {'candidate_id':'stocks:TEST','symbol':'TEST','market':'stocks',
        'conditional_paper_plan':plan,
        'reference_checks':dict(catalogue_candidate='PASS',market_session='PASS',reference_quote='PASS',fx='PASS',exit_deadline=plan['exit_by'],indicative_ask_eur=quote,indicative_bid_eur=quote),
        'technical_checks':dict(state='MEASURED',momentum_20_bars_pct='2',relative_volume_5_vs_15='2',close_above_rolling_vwap=True,trigger_state='WAITING_FOR_TRIGGER'),
        'current_news_source_ids':['news:test'], 'review_sources':{'news:test':{'title':'Synthetic fixture','retrieved_at':NOW.isoformat()}}}


def fixture(monkeypatch):
    # This minimal legacy packet intentionally lacks real chart evidence. Keep
    # legacy reconstruction/immutability tests on their original policy; the v3
    # integration tests use complete captures and test conditional revalidation.
    import market_radar_ai.agents.paper_verdict as pv
    original=pv.build_packets
    def legacy_build(*args,**kwargs):
        batch=original(*args,**kwargs)
        for packet in batch['packets']:
            packet['packet'].pop('review_policy_version',None)
            packet['packet_id']=digest(packet['packet'])
        return batch
    monkeypatch.setattr(pv,'build_packets',legacy_build)
    row=qualified_row()
    import market_radar_ai.agents.qualification as q
    monkeypatch.setattr(q,'qualify',lambda *a,**k:{'candidates':[deepcopy(row)]})
    packet=pv.build_packets({},None,now=NOW)['packets'][0]
    seen=[]
    def ask(stage,prompt,schema):
        seen.append(prompt)
        return dict(stage=stage,packet_id=prompt['packet_id'],verdict='APPROVE_PAPER',
                    rationale='Synthetic test only',source_ids=['news:test'],concerns=[],
                    reviewed_stages=[r['stage'] for r in prompt['peer_reviews']])
    audit=review(packet,{},None,ask,clock=lambda:NOW)
    return row,packet,audit,seen


def test_complete_team_can_produce_paper_watch_without_live_permission(monkeypatch):
    row,packet,audit,seen=fixture(monkeypatch)
    assert len(seen)==8 and all(p['peer_reviews']==[] for p in seen[:6])
    assert len(seen[6]['peer_reviews'])==6 and len(seen[7]['peer_reviews'])==7
    result=finalize(packet,audit,{},None,now=NOW)
    assert result['verdict']=='PAPER_WATCH_FOR_ENTRY' and result['plan']
    assert not result['trade_authorized'] and not result['live_orders_enabled']


@pytest.mark.parametrize('fault',['reject','evidence_gap','missing_role','wrong_packet','changed_plan','expired','bad_cost'])
def test_final_verdict_cannot_override_checks(monkeypatch,fault):
    row,packet,audit,_=fixture(monkeypatch)
    now=NOW
    if fault=='reject':audit['reviews'][3]['verdict']='REJECT'
    if fault=='evidence_gap':audit['reviews'][3]['verdict']='MORE_EVIDENCE_REQUIRED'
    if fault=='missing_role':audit['reviews'].pop()
    if fault=='wrong_packet':audit['reviews'][2]['packet_id']='wrong'
    if fault=='changed_plan':row['conditional_paper_plan']['entry_buffer_bps']='11'
    if fault=='expired':now=NOW+timedelta(minutes=11)
    if fault=='bad_cost':row['conditional_paper_plan']['planned_loss_eur']='0'
    if fault in ('missing_role','wrong_packet'):
        with pytest.raises(ValueError):finalize(packet,audit,{},None,now=now)
    else:
        result=finalize(packet,audit,{},None,now=now)
        assert result['verdict']=='NO_ACTION' and result['plan'] is None


@pytest.mark.parametrize('check',['catalogue_candidate','market_session','reference_quote','fx'])
def test_unknown_reference_blocks_before_ai(check):
    row=qualified_row();row['reference_checks'][check]='UNKNOWN'
    assert not paper_gate(row,now=NOW)['eligible_for_paper_review']


def test_cost_assumptions_are_disclosed_not_unconditional_rejection():
    row=qualified_row()
    result=paper_gate(row,now=NOW)
    assert result['eligible_for_paper_review']
    assert any('assumed 40 bps' in a for a in result['assumptions'])
    row['market']='crypto'
    assert 'crypto_broker_catalogue_not_connected' in paper_gate(row,now=NOW)['paper_blockers']


def test_malformed_citation_never_reaches_finalization(monkeypatch):
    _,packet,_,_=fixture(monkeypatch)
    def bad(stage,prompt,schema):
        return dict(stage=stage,packet_id=packet['packet_id'],verdict='APPROVE_PAPER',rationale='Test',
                    source_ids=['invented'],concerns=[],reviewed_stages=[])
    with pytest.raises(ValueError,match='identity_or_citations'):review(packet,{},None,bad,clock=lambda:NOW)


def test_metered_pipeline_connections_and_durable_duplicate_guard(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from market_radar_ai.agents.paper_verdict import run_pipeline
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from market_radar_ai.agents.github_budget import GitHubSpendingLedger
    from test_github_budget import MemoryStore
    import json
    row,_,_,_=fixture(monkeypatch)
    client=OpenAIPilot(api_key='fake',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='0.9',enabled=True)
    calls=[];deliveries=[];refreshes=[]
    def call(**kw):
        p=json.loads(kw['prompt']);calls.append(p['stage'])
        assert set(kw['schema']['properties'])=={'verdict','rationale','source_ids','concerns'}
        assert kw['schema']['properties']['source_ids']['items']['enum']==p['packet']['source_ids']
        return SimpleNamespace(data=dict(verdict='APPROVE_PAPER',
            rationale='Synthetic pipeline test',source_ids=['news:test'],concerns=[]))
    monkeypatch.setattr(client,'call',call)
    def refresh(symbol):
        assert symbol in ('TEST','SECOND')
        refreshes.append(symbol);return {},None
    def deliver(result):deliveries.append(result);return {'state':'test_receipt'}
    result=run_pipeline({},None,client=client,root=tmp_path/'first',refresh=refresh,deliver=deliver,clock=lambda:NOW,enabled=True)
    assert result['verdict']=='PAPER_WATCH_FOR_ENTRY'
    assert calls==STAGES and len(refreshes)==len(deliveries)==1
    result=run_pipeline({},None,client=client,root=tmp_path/'second',refresh=refresh,deliver=deliver,clock=lambda:NOW,enabled=True)
    assert result['state']=='paper_setup_already_attempted' and len(calls)==8
    assert not deliveries[0]['trade_authorized']

    second=deepcopy(row);second.update(candidate_id='stocks:SECOND',symbol='SECOND')
    second['conditional_paper_plan']['symbol']='SECOND'
    monkeypatch.setattr('market_radar_ai.agents.qualification.qualify',lambda *a,**k:{'candidates':[deepcopy(row),deepcopy(second)]})
    result=run_pipeline({},None,client=client,root=tmp_path/'third',refresh=refresh,deliver=deliver,clock=lambda:NOW,enabled=True)
    assert result['state']=='paper_decision_completed' and len(calls)==16
    assert refreshes==['TEST','SECOND']
    selection=json.loads((tmp_path/'third'/'review-selection.json').read_text())
    assert selection['selected_candidate_id']=='stocks:SECOND'
    assert selection['skipped']==[{'candidate_id':'stocks:TEST','reason':'paper_setup_already_attempted'}]


def test_no_metered_activation_by_default(tmp_path):
    from market_radar_ai.agents.paper_verdict import run_pipeline
    with pytest.raises(ValueError,match='not_enabled'):
        run_pipeline({},None,client=None,root=tmp_path/'run',refresh=None,deliver=None,clock=lambda:NOW)
    assert not (tmp_path/'run').exists()


@pytest.mark.parametrize('field,blocker',[('stop_eur','setup_invalidated_before_entry'),('entry_eur','entry_trigger_already_reached_rebuild')])
def test_current_quote_must_still_be_between_stop_and_trigger(field,blocker):
    row=qualified_row();row['reference_checks']['indicative_ask_eur']=row['conditional_paper_plan'][field]
    assert blocker in paper_gate(row,now=NOW)['paper_blockers']


def test_bid_below_stop_blocks_even_when_ask_remains_above_stop():
    row=qualified_row()
    row['reference_checks']['indicative_bid_eur']=str(Decimal(row['conditional_paper_plan']['stop_eur'])-Decimal('.01'))
    result=paper_gate(row,now=NOW)
    assert not result['eligible_for_paper_review']
    assert 'setup_invalidated_before_entry' in result['paper_blockers']


@pytest.mark.parametrize('bid',[None,'NaN','Infinity','0','-1','bad'])
def test_missing_or_invalid_bid_cannot_pass_paper_gate(bid):
    row=qualified_row();row['reference_checks']['indicative_bid_eur']=bid
    assert 'reference_bid_eur_missing' in paper_gate(row,now=NOW)['paper_blockers']


def test_crossed_quote_and_bid_at_stop_remain_blocked():
    row=qualified_row();checks=row['reference_checks']
    checks['indicative_bid_eur']=str(Decimal(checks['indicative_ask_eur'])+Decimal('.01'))
    assert 'reference_quote_crossed' in paper_gate(row,now=NOW)['paper_blockers']
    checks['indicative_bid_eur']=row['conditional_paper_plan']['stop_eur']
    assert 'setup_invalidated_before_entry' in paper_gate(row,now=NOW)['paper_blockers']


def test_unanimous_review_cannot_approve_a_fresh_bid_below_stop(monkeypatch):
    row,packet,audit,_=fixture(monkeypatch)
    row['reference_checks']['indicative_bid_eur']=str(Decimal(row['conditional_paper_plan']['stop_eur'])-Decimal('.01'))
    result=finalize(packet,audit,{},None,now=NOW)
    assert result['verdict']=='NO_ACTION' and result['plan'] is None
    assert 'fresh_setup_no_longer_qualified' in result['blockers']


@pytest.mark.parametrize('fault',['unknown_source','duplicate_source','forged_metadata'])
def test_metered_invalid_assessments_fail_closed_and_remain_auditable(tmp_path,monkeypatch,fault):
    import json
    from types import SimpleNamespace
    from market_radar_ai.agents.paper_verdict import run_metered
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from market_radar_ai.agents.github_budget import GitHubSpendingLedger
    from test_github_budget import MemoryStore
    _,packet,_,_=fixture(monkeypatch)
    client=OpenAIPilot(api_key='fake',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='0.9',enabled=True)
    answer={'verdict':'APPROVE_PAPER','rationale':'Synthetic test','source_ids':['news:test'],'concerns':[]}
    if fault=='unknown_source':answer['source_ids']=['invented']
    if fault=='duplicate_source':answer['source_ids']*=2
    if fault=='forged_metadata':answer['packet_id']='forged'
    calls=[]
    def call(**kw):calls.append(kw);return SimpleNamespace(data=answer)
    monkeypatch.setattr(client,'call',call)
    path=tmp_path/'review.json'
    with pytest.raises(Exception):run_metered(client,packet,{},None,path=path,clock=lambda:NOW,enabled=True)
    saved=json.loads(path.read_text())
    assert len(calls)==1 and saved['result'] is None
    assert saved['calls'][0]['assessment']==answer
    assert saved['calls'][0]['state']=='failed_review'


def test_unanimous_approval_with_caveats_can_watch_but_any_veto_still_blocks(monkeypatch):
    _,packet,audit,seen=fixture(monkeypatch)
    for report in audit['reviews']:
        report['concerns']=['Reference-price simulation has uncertain fill quality.']
    assert all('non-blocking caveats only' in p['instruction'] for p in seen)
    result=finalize(packet,audit,{},None,now=NOW)
    assert result['verdict']=='PAPER_WATCH_FOR_ENTRY'
    assert not result['trade_authorized']
    for index in range(len(STAGES)):
        for veto in ('REJECT','MORE_EVIDENCE_REQUIRED'):
            changed=deepcopy(audit);changed['reviews'][index]['verdict']=veto
            result=finalize(packet,changed,{},None,now=NOW)
            assert result['verdict']=='NO_ACTION'
            assert 'team_did_not_clear_setup' in result['blockers']


def evidence_fixture(monkeypatch):
    import market_radar_ai.agents.paper_verdict as pv
    row,_,_,_=fixture(monkeypatch)
    row['review_sources'].update({
        'market:old':{'symbol':'TEST','provider':'test','quote_currency':'EUR',
                      'candles':[{'timestamp':NOW.isoformat(),'close':'100'}],
                      'retrieved_at':NOW.isoformat(),'validated_at':NOW.isoformat(),
                      'original_capture_sha256':'a'*64},
        'calendar:old':{'symbol':'TEST','events':[],'status':'empty',
                        'retrieved_at':NOW.isoformat(),'original_calendar_sha256':'b'*64}})
    packet=pv.build_packets({},None,now=NOW)['packets'][0]
    def ask(stage,prompt,schema):
        return dict(stage=stage,packet_id=prompt['packet_id'],verdict='APPROVE_PAPER',
                    rationale='Synthetic evidence test',source_ids=['news:test'],concerns=[],
                    reviewed_stages=[r['stage'] for r in prompt['peer_reviews']])
    audit=review(packet,{},None,ask,clock=lambda:NOW)
    return row,packet,audit


def test_recollection_metadata_and_source_ids_do_not_invalidate_identical_content(monkeypatch):
    from market_radar_ai.agents.paper_verdict import stable_evidence
    row,packet,audit=evidence_fixture(monkeypatch)
    row['review_sources']['news:test'].update(publication_age_seconds=10, published_at=NOW.isoformat(), intraday_recent=True)
    packet['packet']['sources']=deepcopy(row['review_sources'])
    packet['packet_id']=digest(packet['packet'])
    audit['packet_id']=packet['packet_id']
    for report in audit['reviews']:report['packet_id']=packet['packet_id']
    old=deepcopy(row['review_sources'])
    row['review_sources']['news:test']['publication_age_seconds']=11
    for kind in ('market','calendar'):
        source=row['review_sources'].pop(kind+':old')
        source['retrieved_at']=(NOW+timedelta(seconds=1)).isoformat()
        if kind=='market':
            source['validated_at']=(NOW+timedelta(seconds=1)).isoformat()
            source['original_capture_sha256']='c'*64
        else:source['original_calendar_sha256']='d'*64
        row['review_sources'][kind+':new']=source
    assert stable_evidence(old)==stable_evidence(row['review_sources'])
    result=finalize(packet,audit,{},None,now=NOW+timedelta(seconds=1))
    assert result['verdict']=='PAPER_WATCH_FOR_ENTRY'
    # Provenance remains available in the immutable reviewed packet.
    assert packet['packet']['sources']==old


@pytest.mark.parametrize('fault',['candle','news','calendar','provider','unknown_field','missing_source','publication_time','news_freshness'])
def test_material_evidence_changes_still_invalidate_approval(monkeypatch,fault):
    row,packet,audit=evidence_fixture(monkeypatch)
    sources=row['review_sources']
    if fault=='candle':sources['market:old']['candles'][0]['close']='99'
    if fault=='news':sources['news:test']['title']='Changed catalyst'
    if fault=='publication_time':sources['news:test']['published_at']='2026-11-05T12:00:00Z'
    if fault=='news_freshness':sources['news:test']['intraday_recent']=False
    if fault=='calendar':sources['calendar:old']['events']=[{'date':'2026-11-06'}]
    if fault=='provider':sources['market:old']['provider']='different'
    if fault=='unknown_field':sources['market:old']['new_material_field']=True
    if fault=='missing_source':sources.pop('calendar:old')
    result=finalize(packet,audit,{},None,now=NOW)
    assert result['verdict']=='NO_ACTION'
    assert 'evidence_changed_since_review' in result['blockers']


@pytest.mark.parametrize('elapsed,blocked',[(1,True),(899,True),(900,False),(901,False)])
def test_candidate_cooldown_is_sliding_and_survives_changed_setup(monkeypatch,elapsed,blocked):
    from market_radar_ai.agents.paper_verdict import choose_unreviewed_packet
    _,packet,_,_=fixture(monkeypatch)
    _,_,marker,_=choose_unreviewed_packet([packet],{},now=NOW)
    changed=deepcopy(packet);changed['packet']['plan']['entry_eur']='999'
    selected,_,_,skipped=choose_unreviewed_packet([changed],{marker:{}},now=NOW+timedelta(seconds=elapsed))
    assert (selected is None)==blocked
    if blocked:assert skipped[0]['reason']=='paper_review_cooldown'


def test_cooldown_skips_to_different_candidate_and_blocks_future_marker(monkeypatch):
    from market_radar_ai.agents.paper_verdict import choose_unreviewed_packet
    _,packet,_,_=fixture(monkeypatch)
    _,_,marker,_=choose_unreviewed_packet([packet],{},now=NOW+timedelta(seconds=1))
    second=deepcopy(packet);second['packet']['candidate_id']='stocks:OTHER'
    selected,_,_,skipped=choose_unreviewed_packet([packet,second],{marker:{}},now=NOW)
    assert selected==second and len(skipped)==1
    with pytest.raises(ValueError,match='invalid_paper_cooldown_marker'):
        choose_unreviewed_packet([packet],{marker.rsplit(':',1)[0]+':bad':{}},now=NOW)


def test_failed_review_retains_durable_cooldown_without_paid_retry(tmp_path,monkeypatch):
    from market_radar_ai.agents.paper_verdict import run_pipeline
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from market_radar_ai.agents.github_budget import GitHubSpendingLedger
    from test_github_budget import MemoryStore
    row,_,_,_=fixture(monkeypatch)
    client=OpenAIPilot(api_key='fake',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='0.9',enabled=True)
    attempts=[]
    def fail(*a,**k):
        attempts.append(True)
        raise RuntimeError('synthetic_review_failure')
    monkeypatch.setattr('market_radar_ai.agents.paper_verdict.run_metered',fail)
    with pytest.raises(RuntimeError,match='synthetic_review_failure'):
        run_pipeline({},None,client=client,root=tmp_path/'first',refresh=None,deliver=None,clock=lambda:NOW,enabled=True)
    row['review_sources']['news:test']['title']='Changed evidence must not buy an immediate retry'
    result=run_pipeline({},None,client=client,root=tmp_path/'second',refresh=None,deliver=None,clock=lambda:NOW,enabled=True)
    assert result['state']=='paper_review_cooldown' and result['model_calls']==0
    assert len(attempts)==1


def test_budget_pause_records_spent_remaining_and_reserve_separately(tmp_path,monkeypatch):
    import json
    from market_radar_ai.agents.paper_verdict import run_pipeline
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from market_radar_ai.agents.github_budget import GitHubSpendingLedger
    from test_github_budget import MemoryStore
    fixture(monkeypatch)
    store=MemoryStore()
    store.state['entries']['earlier']={'day':NOW.date().isoformat(),'reserved':920875,
                                    'actual':920875,'usage':None}
    client=OpenAIPilot(api_key='fake',ledger=GitHubSpendingLedger(store),eur_per_usd='.9',enabled=True)
    def forbidden(**kw):raise AssertionError('Budget pause must precede model call')
    monkeypatch.setattr(client,'call',forbidden)
    result=run_pipeline({},None,client=client,root=tmp_path/'paused',refresh=None,deliver=None,
                        clock=lambda:NOW,enabled=True)
    assert result['state']=='budget_deferred'
    b=json.loads((tmp_path/'paused'/'budget-headroom.json').read_text())
    assert b['blocking_periods']==['daily']
    assert b['periods']['daily']=={'limit_eur':'1','spent_eur':'0.920875','held_eur':'0','remaining_eur':'0.079125'}
    assert b['required_headroom_eur']=='0.15'
