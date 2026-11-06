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


def discovery():
    return {'discovered_count': 500, 'fallback_used': False, 'failures': [],
            'coverage': {'catalogue_candidates': 500, 'fresh_activity_leads': 30,
                         'candidate_pool': 500, 'technical_checked': 100,
                         'technical_usable': 85, 'technical_unavailable': 15,
                         'technical_deferred': 400, 'research_selected': 19,
                         'research_deferred': 481},
            'universe': {'source': 'trading212_metadata', 'retrieved_at': NOW.isoformat(),
                         'cache_status': 'reused', 'freshness': 'fresh',
                         'symbols': ['SECRET'], 'account_permission_verified': True}}


def test_discovery_counts_reconcile_without_passing_through_catalogue_or_permission(tmp_path):
    write(tmp_path, 'discovery.json', discovery())
    report = build_report(tmp_path, now=NOW)
    result = report['discovery']
    assert result['coverage_status'] == 'validated'
    assert result['coverage'] == discovery()['coverage']
    assert result['universe']['retrieved_at'] == NOW.isoformat()
    assert result['universe']['account_permission_verified'] is False
    assert 'SECRET' not in json.dumps(report)
    summary = markdown(report)
    assert '| Technical checks attempted | 100 |' in summary
    assert '| Technically usable / unavailable | 85 / 15 |' in summary
    assert 'does not mean technically checked, AI reviewed or approved' in summary


def test_premarket_research_is_not_reported_as_technical_checks(tmp_path):
    record = discovery()
    record['coverage'].update(technical_checked=0, technical_usable=0,
                              technical_unavailable=0, technical_deferred=500)
    record['universe'].update(cache_status='reused', freshness='stale_but_valid',
                              retrieved_at='2026-11-04T10:30:00+00:00')
    write(tmp_path, 'discovery.json', record)
    report = build_report(tmp_path, now=NOW)
    assert report['discovery']['coverage_status'] == 'validated'
    assert '| Technical checks attempted | 0 |' in markdown(report)
    assert 'stale_but_valid' in markdown(report)
    assert report['discovery']['universe']['retrieved_at'] == '2026-11-04T10:30:00+00:00'


@pytest.mark.parametrize('field,value', [
    ('technical_checked', True), ('technical_unavailable', -1),
    ('technical_deferred', 399), ('research_deferred', 500),
    ('research_selected', 21), ('catalogue_candidates', 20_001),
    ('fresh_activity_leads', 201), ('technical_usable', '85'),
    ('technical_checked', 101), ('candidate_pool', None),
])
def test_invalid_discovery_counts_cannot_claim_coverage(tmp_path, field, value):
    record = discovery(); record['coverage'][field] = value
    write(tmp_path, 'discovery.json', record)
    report = build_report(tmp_path, now=NOW)
    assert report['discovery']['coverage_status'] == 'invalid'
    assert report['discovery']['coverage'] is None
    assert '| Technical checks attempted |' not in markdown(report)


@pytest.mark.parametrize('stamp', [
    '<script>secret</script>', '2026-11-06T10:30:00', '2026-11-06T10:30:01+00:00', None,
])
def test_invalid_metadata_timestamp_does_not_escape_into_summary(tmp_path, stamp):
    record = discovery()
    record['universe']['retrieved_at'] = stamp
    record['failures'] = ['[secret](https://bad.example)']
    record['coverage']['secret'] = '<script>secret</script>'
    write(tmp_path, 'discovery.json', record)
    report = build_report(tmp_path, now=NOW)
    assert report['discovery']['universe']['retrieved_at'] is None
    assert report['discovery']['universe']['freshness'] == 'unavailable'
    assert 'secret' not in json.dumps(report)
    assert 'bad.example' not in markdown(report)


def test_old_discovery_artifact_keeps_unknown_counts_explicit(tmp_path):
    write(tmp_path, 'discovery.json', {'discovered_count': 9, 'fallback_used': True})
    report = build_report(tmp_path, now=NOW)
    assert report['discovery']['coverage_status'] == 'unavailable'
    assert report['discovery']['coverage'] is None
    assert report['discovery']['fallback_used'] is True
    assert 'no broad-coverage claim' in markdown(report)
