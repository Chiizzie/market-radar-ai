from copy import deepcopy
from datetime import timedelta
import pytest
from test_plan_review import data,answer,NOW
from market_radar_ai.agents.plan_review import prepare,run
from market_radar_ai.dashboard.plan_review import export_review


def bundle():
    from market_radar_ai.market_data.admission import FxQuote
    c,cat,d=data();calls=[]
    d['fx_evidence']=FxQuote.model_validate(d['fx_evidence']).model_dump(mode='json')
    def ask(stage,p,s):
        response=answer(stage,p,s)
        calls.append(dict(stage=stage,state='received',started_at=NOW.isoformat(),received_at=NOW.isoformat(),estimated_cost_microeur=1000,untrusted_response=response))
        return response
    result=run(prepare(c,cat,d),ask,clock=lambda:NOW)
    audit=dict(version='paid-paper-review-v1',state='completed',trade_authorized=False,
               completed_at=NOW.isoformat(),calls=calls,result=result,secret='must not export')
    return c,cat,d,audit


def test_historical_export_preserves_expiry_and_never_authorizes():
    c,cat,d,a=bundle()
    r=export_review(c,cat,d,a,now=NOW+timedelta(hours=1))
    assert r['expired'] and r['expires_at']==d['plan']['expires_at']
    assert len(r['reviews'])==8 and len(r['input_blockers'])==6
    assert r['estimated_review_cost_eur']=='0.008'
    assert not r['trade_authorized'] and not r['live_orders_enabled']
    assert 'secret' not in r and 'calls' not in r

@pytest.mark.parametrize('fault',['plan','citation','prose','result','time','missing','state','cost'])
def test_bad_review_cannot_be_exported(fault):
    c,cat,d,a=bundle()
    if fault=='plan':d['plan']['entry_eur']='1'
    if fault=='citation':a['calls'][0]['untrusted_response']['source_ids']=['fake']
    if fault=='prose':a['calls'][0]['untrusted_response']['rationale']='unfinished so'
    if fault=='result':a['result']['reviews'][0]['verdict']='REJECT'
    if fault=='time':a['calls'][-1]['received_at']=(NOW+timedelta(minutes=6)).isoformat()
    if fault=='missing':del a['calls'][0]['received_at']
    if fault=='state':a['state']='blocked_or_failed'
    if fault=='cost':a['calls'][0]['estimated_cost_microeur']=-1
    with pytest.raises((ValueError,KeyError)):
        export_review(c,cat,d,a,now=NOW+timedelta(hours=1))


def test_completion_after_expiry_rejected():
    c,cat,d,a=bundle()
    a['completed_at']=d['plan']['expires_at']
    with pytest.raises(ValueError,match='invalid_review_timing'):
        export_review(c,cat,d,a,now=NOW+timedelta(hours=1))
