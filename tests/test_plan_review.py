import json
from datetime import timedelta
import pytest
from test_alpaca_paper_rehearsal import packet, NOW
from market_radar_ai.agents.alpaca_paper_rehearsal import build
from market_radar_ai.agents.plan_review import prepare, run


def data():
    c,cat,fx=packet()
    for r in c['bars']['candles']: r['timestamp']=r['timestamp'].isoformat()
    fx['observed_at']=fx['observed_at'].isoformat()
    d=build(c,cat,fx,now=NOW);d['fx_evidence']=fx
    return c,cat,d


def answer(stage,p,schema):
    if stage not in ('debate','conclusion'): assert not p['peer_reviews']
    return dict(snapshot_id=p['snapshot_id'],stage=stage,verdict='MORE_EVIDENCE_REQUIRED',
                rationale='Test response only.',source_ids=[p['snapshot']['source_ids']['plan']],
                acknowledged_blockers=p['snapshot']['blockers'],concerns=['Unresolved evidence.'],
                reviewed_stages=[x['stage'] for x in p['peer_reviews']],trade_authorized=False)


def test_independent_reviews_and_synthesis():
    r=run(prepare(*data()),answer,clock=lambda:NOW)
    assert len(r['reviews'])==8 and not r['trade_authorized']
    assert len(r['reviews'][-1]['reviewed_stages'])==7

@pytest.mark.parametrize('field',['entry_eur','quantity','planned_loss_eur'])
def test_altered_plan_rejected(field):
    c,cat,d=data();d['plan'][field]='1'
    with pytest.raises(ValueError):prepare(c,cat,d)


def test_expiry_and_fabricated_citations():
    p=prepare(*data())
    with pytest.raises(ValueError):run(p,answer,clock=lambda:NOW+timedelta(minutes=5))
    def bad(stage,p,s):
        r=answer(stage,p,s);r['source_ids']=['invented'];return r
    with pytest.raises(ValueError):run(p,bad,clock=lambda:NOW)


def test_paid_adapter_requires_explicit_durable_client(tmp_path):
    from market_radar_ai.agents.plan_review import run_paid
    with pytest.raises(ValueError):
        run_paid(object(),prepare(*data()),path=tmp_path/'review.json',clock=lambda:NOW,enabled=True)
    assert not (tmp_path/'review.json').exists()


def test_blockers_cannot_be_cleared_by_model():
    def bad(stage,p,s):
        r=answer(stage,p,s);r['acknowledged_blockers']=[];return r
    with pytest.raises(ValueError):run(prepare(*data()),bad,clock=lambda:NOW)


def test_paid_audit_preserves_returned_usage_on_rejection(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import market_radar_ai.agents.openai_pilot as pilot
    import market_radar_ai.agents.github_budget as budget
    from market_radar_ai.agents.plan_review import run_paid
    class Ledger: pass
    class Client:
        ledger=Ledger()
        def call(self,**kwargs):
            p=json.loads(kwargs['prompt'])
            props=kwargs['schema']['properties']
            assert props['snapshot_id']['enum']==[p['snapshot_id']]
            assert props['stage']['enum']==[p['stage']]
            assert props['reviewed_stages']['maxItems']==0
            assert props['acknowledged_blockers']['minItems']==len(p['snapshot']['blockers'])
            reply=answer(p['stage'],p,kwargs['schema'])
            reply['source_ids']=['fabricated']
            return SimpleNamespace(data=reply,response_id='test',cost_usd='0.01',estimated_cost_microeur=9000,input_tokens=1000,counted_input_tokens=1000)
    monkeypatch.setattr(pilot,'OpenAIPilot',Client)
    monkeypatch.setattr(budget,'GitHubSpendingLedger',Ledger)
    path=tmp_path/'audit.json'
    with pytest.raises(RuntimeError):run_paid(Client(),prepare(*data()),path=path,clock=lambda:NOW,enabled=True)
    audit=json.loads(path.read_text())
    assert audit['state']=='blocked_or_failed' and len(audit['calls'])==1
    assert audit['calls'][0]['estimated_cost_microeur']==9000
    assert audit['result'] is None
    assert audit['calls'][0]['untrusted_response']['source_ids']==['fabricated']
    assert audit['validation_details']==[{'type':'review_identity_or_evidence_mismatch'}]


def test_oversized_evidence_stops_before_first_model_call():
    c,cat,d=data();c['extra_context']='x'*33000
    def never(*args):pytest.fail('oversized prompt reached model adapter')
    with pytest.raises(ValueError,match='review_prompt_too_large'):
        run(prepare(c,cat,d),never,clock=lambda:NOW)


def test_peer_compaction_preserves_reasoning_and_shared_blockers():
    def inspect(stage,p,schema):
        if p['peer_reviews']:
            assert all(set(r)=={'stage','verdict','rationale','source_ids','concerns'} for r in p['peer_reviews'])
            assert all(r['rationale']=='Test response only.' and r['concerns']==['Unresolved evidence.'] for r in p['peer_reviews'])
            assert len(p['snapshot']['blockers'])==6
        return answer(stage,p,schema)
    run(prepare(*data()),inspect,clock=lambda:NOW)

@pytest.mark.parametrize('bad',['Ends mid sentence so','Trailing space. ','Bad\ftext.','Source market:abcd reviewed.'])
def test_incomplete_or_corrupted_prose_rejected(bad):
    def malformed(stage,p,s):
        r=answer(stage,p,s);r['rationale']=bad;return r
    with pytest.raises(ValueError):run(prepare(*data()),malformed,clock=lambda:NOW)
