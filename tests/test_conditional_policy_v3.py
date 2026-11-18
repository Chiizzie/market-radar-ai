from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest
from test_pullback_strategy import synthetic_setup
from market_radar_ai.agents import qualification as q
from market_radar_ai.agents.paper_verdict import build_packets,finalize,STAGES
from market_radar_ai.agents.conditional_revalidation import revalidate
from market_radar_ai.agents.paper_review_prompts import VERSION


def fixture():
    doc,feed,now=synthetic_setup();packet=build_packets(doc,feed,now=now)['packets'][0]
    audit={'schema_version':'paper-ai-review-v1','packet_id':packet['packet_id'],'completed_at':now.isoformat(),
           'model_calls':8,'trade_authorized':False,'reviews':[
        {'stage':s,'packet_id':packet['packet_id'],'verdict':'APPROVE_PAPER','rationale':'Synthetic conditional watch',
         'source_ids':[packet['packet']['source_ids'][0]],'concerns':[],'reviewed_stages':STAGES[:i] if i>=6 else []}
        for i,s in enumerate(STAGES)]}
    return doc,feed,now,packet,audit


def test_chief_can_resolve_uncertainty_but_every_hard_veto_survives():
    d,f,n,p,a=fixture();assert p['packet']['review_policy_version']==VERSION
    a['reviews'][3]['verdict']='MORE_EVIDENCE_REQUIRED'
    r=finalize(p,a,d,f,now=n);assert r['verdict']=='PAPER_WATCH_FOR_ENTRY'
    assert r['plan']['entry_eur']==p['packet']['plan']['entry_eur']
    for i in range(8):
        b=deepcopy(a);b['reviews'][i]['verdict']='REJECT'
        assert finalize(p,b,d,f,now=n)['verdict']=='NO_ACTION'
    a['reviews'][-1]['verdict']='MORE_EVIDENCE_REQUIRED'
    assert finalize(p,a,d,f,now=n)['verdict']=='NO_ACTION'


def test_initial_volume_is_not_a_repeat_admission_gate(monkeypatch):
    d,f,n,p,a=fixture();fresh=q.qualify(d,f,now=n)
    row=fresh['candidates'][0];row['technical_checks']['relative_volume_5_vs_15']='0.9'
    row['paper_blockers']=['relative_volume_below_strategy_minimum']
    monkeypatch.setattr(q,'qualify',lambda *args,**kwargs:deepcopy(fresh))
    assert finalize(p,a,d,f,now=n)['verdict']=='PAPER_WATCH_FOR_ENTRY'


@pytest.mark.parametrize('fault',['stop','spread','gap','news','calendar','bars','missing_fx','missing_market','vwap','deadline'])
def test_fresh_hard_failures_cannot_be_overridden_by_chief(monkeypatch,fault):
    d,f,n,p,a=fixture();fresh=q.qualify(d,f,now=n);r=fresh['candidates'][0]
    if fault=='stop':r['reference_checks']['indicative_bid_eur']=p['packet']['plan']['stop_eur']
    elif fault=='spread':r['reference_checks']['indicative_bid_eur']=str(Decimal(r['reference_checks']['indicative_ask_eur'])*Decimal('.99'))
    elif fault=='gap':r['reference_checks']['indicative_ask_eur']=str(Decimal(p['packet']['plan']['entry_eur'])*Decimal('1.01'))
    elif fault=='news':r['review_sources']['news:new']={'title':'New adverse event','published_at':n.isoformat()}
    elif fault=='calendar':r['review_sources']['calendar:new']={'events':[{'date':n.date().isoformat()}]}
    elif fault=='bars':next(v for k,v in r['review_sources'].items() if k.startswith('market:'))['candles'][-1]['close']='1'
    elif fault=='missing_fx':r['reference_checks']['fx']='UNKNOWN'
    elif fault=='missing_market':r['reference_checks']['market_session']='FAIL'
    elif fault=='vwap':r['technical_checks']['close_above_rolling_vwap']=False
    elif fault=='deadline':n+=timedelta(seconds=181)
    monkeypatch.setattr(q,'qualify',lambda *args,**kwargs:deepcopy(fresh))
    result=finalize(p,a,d,f,now=n);assert result['verdict']=='NO_ACTION' and result['plan'] is None


def test_watch_lifetime_is_bounded_and_original_economics_are_frozen():
    d,f,n,p,a=fixture();plan,blocks=revalidate(p['packet'],d,f,now=n)
    assert not blocks
    from datetime import datetime
    assert datetime.fromisoformat(plan['expires_at'])<=n+timedelta(seconds=180)
    assert {k:v for k,v in plan.items() if k!='expires_at'}=={k:v for k,v in p['packet']['plan'].items() if k!='expires_at'}
