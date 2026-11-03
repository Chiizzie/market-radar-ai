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
