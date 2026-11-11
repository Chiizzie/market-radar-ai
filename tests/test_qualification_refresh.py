from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from test_pullback_strategy import synthetic_setup
from test_scheduled_review import ENV
from market_radar_ai.agents import qualification_refresh as qr, paper_dispatch as dispatch
from market_radar_ai.agents.paper_verdict import build_packets
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.dashboard.api_budget import unavailable


def fresh_record(old,now):
    record=deepcopy(old);p=record['payload'];p['retrieved_at']=now.isoformat()
    p['market_clock']['timestamp']=now.isoformat()
    p['fx']['observed_at']=now.isoformat()
    for quote in p['quotes']['quotes'].values():quote['t']=now.isoformat()
    record['payload_sha256']=digest(p)
    return record


def test_replay_delay_refreshes_checks_without_restamping_history(monkeypatch):
    doc,feed,now=synthetic_setup();original=deepcopy(doc);late=now+timedelta(seconds=168)
    assert build_packets(doc,feed,now=now)['packets']
    assert not build_packets(doc,feed,now=late)['packets']
    seen=[]
    def collect(symbols,**kw):
        seen.append(kw)
        return fresh_record(kw['catalogue_record'],late)
    monkeypatch.setattr(qr,'collect',collect)
    fresh,audit=qr.refresh_current_inputs(doc,env={'ALPACA_API_KEY':'key','OPENAI_API_KEY':'forbidden'},clock=lambda:late,force=True)
    assert build_packets(fresh,feed,now=late)['packets']
    assert doc==original and fresh['captures']==original['captures']
    assert seen[0]['env']=={'ALPACA_API_KEY':'key'}
    assert audit['refreshed_fields']==['stock_reference_checks']


def test_still_stale_provider_quote_never_gets_relabelled_current(monkeypatch):
    doc,feed,now=synthetic_setup();late=now+timedelta(seconds=168)
    monkeypatch.setattr(qr,'collect',lambda *a,**kw:deepcopy(doc['stock_reference_checks']))
    fresh,_=qr.refresh_current_inputs(doc,env={},clock=lambda:late,force=True)
    assert not build_packets(fresh,feed,now=late)['packets']


def test_stale_budget_refreshed_before_quotes_and_failure_is_unknown(monkeypatch):
    doc,_,now=synthetic_setup();late=now+timedelta(seconds=400)
    doc['api_budget']=unavailable(now);order=[]
    def budget(*a,**kw):order.append('budget');return unavailable(late)
    def quotes(*a,**kw):order.append('quotes');return fresh_record(doc['stock_reference_checks'],late)
    monkeypatch.setattr(qr,'read_summary',budget);monkeypatch.setattr(qr,'collect',quotes)
    fresh,_=qr.refresh_current_inputs(doc,env={},clock=lambda:late)
    assert order==['budget','quotes']
    assert fresh['api_budget']['status']=='unavailable' and fresh['api_budget']['periods'] is None
    assert doc['api_budget']['as_of']==now.isoformat()


def test_dispatch_refreshes_after_sync_before_pipeline(monkeypatch,tmp_path):
    import market_radar_ai.agents.comparison_live as live
    doc,feed,now=synthetic_setup();current=[now];order=[]
    class Comparison:
        def __init__(self,*a,**kw):pass
        def sync(self):order.append('sync');current[0]+=timedelta(seconds=168)
        def close(self):order.append('close')
    monkeypatch.setattr(live,'LiveComparison',Comparison)
    monkeypatch.setattr(live,'EventClient',lambda *a,**kw:object())
    monkeypatch.setattr(dispatch,'YahooFxProvider',lambda:SimpleNamespace(fetch=lambda *a,**kw:SimpleNamespace(eur_per_unit='.9')))
    monkeypatch.setattr(dispatch,'OpenAIPilot',lambda **kw:SimpleNamespace(ledger=kw['ledger']))
    monkeypatch.setattr(qr,'collect',lambda *a,**kw:fresh_record(kw['catalogue_record'],current[0]))
    def pipeline(document,feed,**kw):
        order.append('pipeline');assert build_packets(document,feed,now=current[0])['packets']
        assert document['captures']==doc['captures']
        kw['root'].mkdir();return {'model_calls':0}
    monkeypatch.setattr(dispatch,'run_pipeline',pipeline)
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.permitted',lambda *a:True)
    result=dispatch.execute(doc,feed,tmp_path/'run',env={**ENV,'PAPER_FINAL_VERDICTS':'true','PAPER_COMPARISON_ENABLED':'true','GH_BUDGET_TOKEN':'synthetic'},clock=lambda:current[0])
    assert order==['sync','pipeline','close'] and result['model_calls']==0
    assert (tmp_path/'run'/'qualification-refresh.json').exists()
