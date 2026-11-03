from copy import deepcopy
from datetime import timedelta
import json
from types import SimpleNamespace
import pytest

from test_candidate_packages import stock_capture, feed
from test_capture_shortlist import capture, NOW
from market_radar_ai.agents.candidate_packages import build_packages, digest
from market_radar_ai.agents.candidate_review import run, run_paid, STAGES, prompt_snapshot
from market_radar_ai.agents.github_candidate_review import execute

ENV = {'GITHUB_REPOSITORY':'Chiizzie/market-radar-ai',
       'GITHUB_REF':'refs/heads/phase-1/market-data-layer',
       'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_RUN_ATTEMPT':'1'}


def package(d=None, f=None):
    d = d or capture()
    return build_packages(d, f, now=NOW)['packages'][0]


def answer(stage, p, schema):
    return dict(snapshot_id=p['snapshot_id'],stage=stage,verdict='MORE_EVIDENCE_REQUIRED',
                rationale='Research only. Further evidence is required.',
                source_ids=[p['snapshot']['source_ids'][0]],
                acknowledged_blockers=p['snapshot']['missing_evidence'],
                concerns=['Broker eligibility remains unknown.'],
                reviewed_stages=[x['stage'] for x in p['peer_reviews']],trade_authorized=False)


@pytest.mark.parametrize('data,news',[(capture(),None),(stock_capture(),feed())])
def test_generic_eight_stage_connection_and_isolation(data,news):
    record=package(data,news); original=deepcopy(record); calls=[]
    def ask(stage,p,s):
        assert [r['stage'] for r in p['peer_reviews']] == (calls[:] if stage in ('debate','conclusion') else [])
        calls.append(stage)
        result=answer(stage,p,s)
        p['snapshot']['symbol']='MUTATION'
        return result
    r=run(record,data,news,ask,clock=lambda:NOW)
    assert calls==STAGES and r['state']=='research_review_completed'
    assert r['candidate_id']==record['package']['candidate_id']
    assert r['plan'] is None and not r['trade_authorized']
    assert record==original


@pytest.mark.parametrize('field,value',[
    ('source_ids',['news:invented']), ('stage','other'), ('snapshot_id','other'),
    ('acknowledged_blockers',[]), ('reviewed_stages',['other']), ('trade_authorized',True),
    ('verdict','BUY'),
])
def test_rejects_unsupported_review(field,value):
    calls=[]
    def bad(stage,p,s):
        calls.append(stage);r=answer(stage,p,s);r[field]=value;return r
    with pytest.raises(ValueError):run(package(),capture(),None,bad,clock=lambda:NOW)
    assert len(calls)==1


def test_rehashed_but_changed_package_rejected_before_model():
    r=package();r['package']['missing_evidence']=[];r['package_id']=digest(r['package'])
    with pytest.raises(ValueError,match='does_not_reproduce'):
        run(r,capture(),None,lambda *a:pytest.fail('model called'),clock=lambda:NOW)


def test_stale_start_rejected_and_review_can_finish_only_as_stale_research():
    with pytest.raises(ValueError,match='expired'):
        run(package(),capture(),None,lambda *a:pytest.fail('model called'),clock=lambda:NOW+timedelta(seconds=60))
    current=[NOW];seen=[]
    def ask(stage,p,s):
        seen.append(p['evidence_status']);current[0]+=timedelta(seconds=15)
        return answer(stage,p,s)
    r=run(package(),capture(),None,ask,clock=lambda:current[0])
    assert r['evidence_status']=='STALE_RESEARCH_ONLY' and seen[-1]=='STALE_RESEARCH_ONLY'
    assert r['evidence_expires_at']==package()['package']['expires_at']
    assert len(r['reviews'])==8 and not r['trade_authorized']


def test_deadline_stops_without_retry():
    current=[NOW];calls=[]
    def slow(stage,p,s):
        calls.append(stage);current[0]+=timedelta(minutes=10);return answer(stage,p,s)
    with pytest.raises(ValueError,match='deadline'):
        run(package(),capture(),None,slow,clock=lambda:current[0])
    assert len(calls)==1


def test_lossless_prompt_compaction():
    body=package()['package']; original=deepcopy(body)
    compact=prompt_snapshot(body)
    sid=body['source_ids'][0]; encoded=compact['sources'][sid]['candles']
    assert [dict(zip(encoded['columns'],r)) for r in encoded['rows']]==body['sources'][sid]['candles']
    assert body==original


def test_paid_requires_real_durable_adapter(tmp_path):
    with pytest.raises(ValueError,match='not_enabled'):
        run_paid(object(),package(),capture(),None,path=tmp_path/'audit.json',clock=lambda:NOW,enabled=True)
    assert not list(tmp_path.iterdir())


def test_paid_adapter_preserves_cost_even_when_citation_rejected(tmp_path,monkeypatch):
    import market_radar_ai.agents.openai_pilot as pilot
    import market_radar_ai.agents.github_budget as budget
    class Ledger: pass
    class Client:
        ledger=Ledger()
        def call(self,**kw):
            p=json.loads(kw['prompt']);props=kw['schema']['properties']
            assert props['source_ids']['items']['enum']==p['snapshot']['source_ids']
            assert kw['request_id'].startswith('candidate-review-v1:')
            r=answer(p['stage'],p,kw['schema']);r['source_ids']=['invented']
            return SimpleNamespace(data=r,response_id='test',cost_usd='0.01',estimated_cost_microeur=9000,
                                   input_tokens=1000,output_tokens=100,counted_input_tokens=1000)
    monkeypatch.setattr(pilot,'OpenAIPilot',Client)
    monkeypatch.setattr(budget,'GitHubSpendingLedger',Ledger)
    path=tmp_path/'review.json'
    with pytest.raises(RuntimeError):run_paid(Client(),package(),capture(),None,path=path,clock=lambda:NOW,enabled=True)
    audit=json.loads(path.read_text())
    assert audit['state']=='blocked_or_failed' and audit['result'] is None
    assert len(audit['calls'])==1 and audit['calls'][0]['estimated_cost_microeur']==9000
    assert audit['validation_details']==[{'type':'review_identity_or_evidence_mismatch'}]


def test_manual_runner_dry_run_selects_one_and_never_builds_client(tmp_path,monkeypatch):
    import market_radar_ai.agents.github_candidate_review as module
    monkeypatch.setattr(module,'OpenAIPilot',lambda **kw:pytest.fail('paid client created'))
    r=execute(capture(),None,tmp_path/'run',env=ENV,clock=lambda:NOW)
    assert r['state']=='ready_dry_run' and r['model_calls']==0
    assert r['candidate_id'].startswith('crypto:')
    assert not (tmp_path/'run'/'review.json').exists()


@pytest.mark.parametrize('override',[{'GITHUB_REPOSITORY':'Chiizzie/market-radar'},
    {'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_EVENT_NAME':'push'},{'CANDIDATE_MARKET':'NVDA'}])
def test_manual_runner_guards(tmp_path,override):
    with pytest.raises(ValueError):execute(capture(),None,tmp_path/'run',env={**ENV,**override},clock=lambda:NOW)
    assert not (tmp_path/'run').exists()


def test_no_candidates_is_honest_zero_calls(tmp_path):
    r=execute(capture(),None,tmp_path/'run',env=ENV,clock=lambda:NOW+timedelta(hours=1))
    assert r['state']=='no_reviewable_candidate' and r['model_calls']==0
