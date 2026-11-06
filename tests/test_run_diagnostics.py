from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from market_radar_ai.dashboard.run_diagnostics import build_report, markdown, spending
from market_radar_ai.agents.github_budget import initial_state
from market_radar_ai.agents.candidate_packages import digest

NOW=datetime(2026,11,6,10,30,tzinfo=timezone.utc)


def write(root,name,value):
    root.mkdir(parents=True,exist_ok=True);(root/name).write_text(json.dumps(value))


def qualification():
    return {'selection':{'markets':{'stocks':{'attempted':3,'rankable':2,'shortlisted':2,'deferred_by_limit':0,
            'rejected':[{'symbol':'GAP','reason':'insufficient_history'}]}}},
            'candidates':[{'candidate_id':'stocks:ONE','paper_blockers':['relative_volume_below_1_5','current_symbol_linked_news_missing','relative_volume_below_1_5'],'eligible_for_paper_review':False},
                          {'candidate_id':'stocks:TWO','paper_blockers':[],'eligible_for_paper_review':True}]}


def test_counts_each_blocker_once_and_keeps_precapture_rejections(tmp_path):
    write(tmp_path,'qualification.json',qualification())
    r=build_report(tmp_path,now=NOW)
    assert len(r['candidates'])==3 and r['coverage']['stocks']['attempted']==3
    assert r['blocker_counts']['relative_volume_below_1_5']==1
    assert r['blocker_groups']=={'capture_quality_or_history':1,'setup_conditions':1,'evidence_or_validation_gap':1}
    assert r['spending']['generation_records']==0 and r['model_calls_by_diagnostics']==0
    assert not r['trade_authorized'] and not r['review']['validated_eight_stage_review']
    assert 'Ready for review only' in markdown(r)


def test_missing_review_uses_labelled_collection_fallback_not_fake_success(tmp_path):
    collect=tmp_path/'collect';review=tmp_path/'review';write(collect,'qualification.json',qualification())
    r=build_report(collect,review,now=NOW)
    assert r['qualification_origin']=='collection_fallback_not_review_confirmation'
    assert r['review']['state']=='not_confirmed'
    assert r['spending']['settled_estimated_eur'] is None
    assert 'unavailable' in markdown(r)


@pytest.mark.parametrize('state',['no_qualified_candidate_zero_cost','paper_review_cooldown','budget_deferred','paper_setup_already_attempted'])
def test_confirmed_zero_runs_never_access_budget(tmp_path,state):
    def forbidden():raise AssertionError('No budget lookup required')
    write(tmp_path,'status.json',{'state':state,'model_calls':0})
    r=build_report(tmp_path,tmp_path,now=NOW,budget_loader=forbidden)
    assert r['spending']['status']=='confirmed_zero_model_calls'


def test_partial_attempt_and_delivery_failure_remain_visible(tmp_path):
    write(tmp_path,'review.json',{'calls':[{'stage':'opportunity_hunter','assessment':{}}, {'stage':'technical_analyst','state':'failed_review'}],'result':None})
    r=build_report(tmp_path,tmp_path,now=NOW)
    assert r['review']['stages_started']==2 and r['review']['stages_with_assessments']==1
    assert r['review']['last_stage']=='technical_analyst' and not r['review']['validated_eight_stage_review']
    assert r['review']['telegram_delivery']=='not_confirmed'
    assert r['spending']['reconciliation_required']


def test_completed_review_does_not_imply_confirmed_delivery(tmp_path,monkeypatch):
    from test_paper_verdict import fixture
    _,packet,audit,_=fixture(monkeypatch)
    write(tmp_path,'packet.json',packet);write(tmp_path,'review.json',{'calls':[],'result':audit})
    r=build_report(tmp_path,tmp_path,now=NOW)
    assert r['review']['validated_eight_stage_review']
    assert r['review']['dashboard_delivery']=='not_confirmed'
    audit['reviews'][-1]['packet_id']='bad';write(tmp_path,'review.json',{'result':audit})
    assert not build_report(tmp_path,tmp_path,now=NOW)['review']['validated_eight_stage_review']


def test_only_packet_spend_is_counted_and_unsettled_holds_are_not_charges():
    body={'synthetic':True};packet={'packet':body,'packet_id':digest(body)}
    prefix='paper-final-v1:'+packet['packet_id']+':'
    state=initial_state()
    state['entries']={prefix+'one':{'day':'2026-11-06','reserved':20000,'actual':12375,'usage':None},
                      prefix+'two':{'day':'2026-11-06','reserved':30000,'actual':None,'usage':None},
                      'unrelated':{'day':'2026-11-06','reserved':500000,'actual':500000,'usage':None}}
    r=spending(packet,{}, {'calls':[]},budget_loader=lambda:(state,'a'*40))
    assert r['settled_estimated_eur']=='0.012375' and r['held_maximum_eur']=='0.03'
    assert r['reconciliation_required'] and r['generation_records']==0
    def fail():raise RuntimeError('SECRET')
    r=spending(packet,{}, {},budget_loader=fail)
    assert r['settled_estimated_eur'] is None and 'SECRET' not in str(r)


def test_corrupt_files_and_untrusted_labels_are_not_rendered(tmp_path):
    q=qualification();q['candidates'][0]['candidate_id']='<script>alert(1)</script>'
    q['candidates'][0]['paper_blockers']=['[click](https://evil.example)']
    write(tmp_path,'qualification.json',q);(tmp_path/'status.json').write_text('bad JSON')
    r=build_report(tmp_path,tmp_path,now=NOW)
    assert r['unreadable_artifacts']==['status.json']
    assert 'script' not in markdown(r) and 'evil.example' not in markdown(r)


def test_full_report_from_actual_crypto_failure_replay_if_available(tmp_path):
    # A portable regression: four assessments and a fifth attempt are not five model calls.
    write(tmp_path,'review.json',{'calls':[{'stage':s,'assessment':{'verdict':'APPROVE_PAPER'}} for s in
        ('opportunity_hunter','technical_analyst','news_analyst','devils_advocate')]+[{'stage':'risk_manager','state':'failed_review'}],'result':None})
    r=build_report(tmp_path,tmp_path,now=NOW)
    assert r['review']['stages_with_assessments']==4 and r['review']['stages_started']==5
    assert not r['review']['validated_eight_stage_review'] and r['spending']['generation_records'] is None
