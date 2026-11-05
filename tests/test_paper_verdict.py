from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest
from market_radar_ai.agents.paper_verdict import build_packets, review, finalize, paper_gate, STAGES
from market_radar_ai.agents.candidate_packages import digest
from test_setup_checks import plan_and_bars, NOW


def qualified_row():
    plan,_=plan_and_bars();plan['symbol']='TEST'
    return {'candidate_id':'stocks:TEST','symbol':'TEST','market':'stocks',
        'conditional_paper_plan':plan,
        'reference_checks':dict(catalogue_candidate='PASS',market_session='PASS',reference_quote='PASS',fx='PASS',exit_deadline=plan['exit_by'],indicative_ask_eur=str((Decimal(plan['stop_eur'])+Decimal(plan['entry_eur']))/2)),
        'technical_checks':dict(state='MEASURED',momentum_20_bars_pct='2',relative_volume_5_vs_15='2',close_above_rolling_vwap=True,trigger_state='WAITING_FOR_TRIGGER'),
        'current_news_source_ids':['news:test'], 'review_sources':{'news:test':{'title':'Synthetic fixture','retrieved_at':NOW.isoformat()}}}


def fixture(monkeypatch):
    row=qualified_row()
    import market_radar_ai.agents.qualification as q
    monkeypatch.setattr(q,'qualify',lambda *a,**k:{'candidates':[deepcopy(row)]})
    packet=build_packets({},None,now=NOW)['packets'][0]
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


@pytest.mark.parametrize('fault',['reject','concern','missing_role','wrong_packet','changed_plan','expired','bad_cost'])
def test_final_verdict_cannot_override_checks(monkeypatch,fault):
    row,packet,audit,_=fixture(monkeypatch)
    now=NOW
    if fault=='reject':audit['reviews'][3]['verdict']='REJECT'
    if fault=='concern':audit['reviews'][3]['concerns']=['Unresolved problem']
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
    fixture(monkeypatch)
    client=OpenAIPilot(api_key='fake',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='0.9',enabled=True)
    calls=[];deliveries=[];refreshes=[]
    def call(**kw):
        p=json.loads(kw['prompt']);calls.append(p['stage'])
        assert set(kw['schema']['properties'])=={'verdict','rationale','source_ids','concerns'}
        assert kw['schema']['properties']['source_ids']['items']['enum']==p['packet']['source_ids']
        return SimpleNamespace(data=dict(verdict='APPROVE_PAPER',
            rationale='Synthetic pipeline test',source_ids=['news:test'],concerns=[]))
    monkeypatch.setattr(client,'call',call)
    def refresh():refreshes.append(True);return {},None
    def deliver(result):deliveries.append(result);return {'state':'test_receipt'}
    result=run_pipeline({},None,client=client,root=tmp_path/'first',refresh=refresh,deliver=deliver,clock=lambda:NOW,enabled=True)
    assert result['verdict']=='PAPER_WATCH_FOR_ENTRY'
    assert calls==STAGES and len(refreshes)==len(deliveries)==1
    result=run_pipeline({},None,client=client,root=tmp_path/'second',refresh=refresh,deliver=deliver,clock=lambda:NOW,enabled=True)
    assert result['state']=='paper_setup_already_attempted' and len(calls)==8
    assert not deliveries[0]['trade_authorized']


def test_no_metered_activation_by_default(tmp_path):
    from market_radar_ai.agents.paper_verdict import run_pipeline
    with pytest.raises(ValueError,match='not_enabled'):
        run_pipeline({},None,client=None,root=tmp_path/'run',refresh=None,deliver=None,clock=lambda:NOW)
    assert not (tmp_path/'run').exists()


@pytest.mark.parametrize('field,blocker',[('stop_eur','setup_invalidated_before_entry'),('entry_eur','entry_trigger_already_reached_rebuild')])
def test_current_quote_must_still_be_between_stop_and_trigger(field,blocker):
    row=qualified_row();row['reference_checks']['indicative_ask_eur']=row['conditional_paper_plan'][field]
    assert blocker in paper_gate(row,now=NOW)['paper_blockers']


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
