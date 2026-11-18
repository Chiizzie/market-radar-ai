"""Offline acceptance paths. Synthetic evidence, no paid requests or live outcomes."""
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
import json
import pytest
from market_radar_ai.agents.paper_verdict import run_pipeline, STAGES
from market_radar_ai.agents.paper_tracking import PaperTracker
from market_radar_ai.agents.paper_outcomes import Quote
from market_radar_ai.agents.openai_pilot import OpenAIPilot
from market_radar_ai.agents.github_budget import GitHubSpendingLedger
from test_github_budget import MemoryStore
from test_paper_verdict import fixture, NOW

@pytest.mark.parametrize('case',['target','stop_gap','deadline','missing_deadline','expired_without_entry','veto'])
def test_complete_decision_delivery_and_persistent_outcome(tmp_path,monkeypatch,case):
    fixture(monkeypatch)
    client=OpenAIPilot(api_key='synthetic',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='0.9',enabled=True)
    stages=[];archives=[]
    def call(**kw):
        p=json.loads(kw['prompt']);stages.append(p['stage'])
        return SimpleNamespace(data={'verdict':'REJECT' if case=='veto' and len(stages)==4 else 'APPROVE_PAPER',
          'rationale':'Synthetic acceptance only','source_ids':['news:test'],'concerns':[]})
    monkeypatch.setattr(client,'call',call)
    def deliver(a):archives.append(a);return {'state':'synthetic_receipt'}
    root=tmp_path/'attempt'
    result=run_pipeline({},None,client=client,root=root,refresh=lambda s:({},None),deliver=deliver,clock=lambda:NOW,enabled=True)
    assert stages==STAGES and len(archives)==1
    assert archives[0]['trade_authorized'] is False
    if case=='veto':
        assert result['verdict']=='NO_ACTION'
        assert not (root/'paper-journal.sqlite').exists()
        return
    tracker=PaperTracker(root/'paper-journal.sqlite');decision=archives[0]['decision'];p=decision['plan'];key=decision['packet_id']
    assert tracker.report(now=NOW)['trades'][0]['state']=='watching'
    end=datetime.fromisoformat(p['exit_by'])
    def observe(at,value):
        q=Quote(observed_at=at,bid=value,ask=value);tracker.observe(key,q,symbol=p['symbol'],source='synthetic',now=at)
    if case!='expired_without_entry':observe(NOW+timedelta(seconds=1),p['entry_eur'])
    if case in ('target','stop_gap','deadline'):
        value=Decimal(p['target_eur']) if case=='target' else Decimal(p['stop_eur'])-1 if case=='stop_gap' else Decimal(p['entry_eur'])
        observe(end if case=='deadline' else NOW+timedelta(seconds=2),value)
    tracker=PaperTracker(root/'paper-journal.sqlite')
    o=tracker.report(now=end+timedelta(seconds=1))['trades'][0]['outcome']
    if case=='expired_without_entry':assert o['status']=='not_filled' and o['net_pnl_eur'] is None
    elif case=='missing_deadline':assert o['status']=='unresolved' and o['net_pnl_eur'] is None
    else:
        assert o['status']=='closed'
        expected=(value-Decimal(p['entry_eur']))*Decimal(p['quantity'])-Decimal(p['assumed_round_trip_cost_eur'])
        assert Decimal(o['net_pnl_eur'])==expected
        if case=='stop_gap':assert Decimal(o['exit_fill'])<Decimal(p['stop_eur'])

def test_hundred_stock_screen_is_not_eight_stock_watchlist(monkeypatch):
    from market_radar_ai.market_data.discovery import discover
    from test_discovery import NOW as OPEN
    symbols=['S'+str(i) for i in range(150)]
    class Session:
        def get(self,url,**kw):
            data={'last_updated':OPEN.isoformat(),'most_actives':[{'symbol':s} for s in symbols[:100]],
                  'gainers':[{'symbol':s} for s in symbols[100:]],'losers':[]}
            class Response:
                status_code=200
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def iter_content(self,n):yield json.dumps(data).encode()
            return Response()
    checked=[]
    monkeypatch.setattr('market_radar_ai.market_data.providers.catalogues.Trading212Catalogue.fetch',lambda self:[SimpleNamespace(ticker=s+'_US_EQ',type='STOCK',currencyCode='USD') for s in symbols])
    def history(self,s):checked.append(s);return s
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca.AlpacaIexProvider.fetch_history',history)
    monkeypatch.setattr('market_radar_ai.market_data.capture.capture_result',lambda r,**k:{'payload':{'quality_passed_at_capture':True}})
    env={'ALPACA_API_KEY':'synthetic','ALPACA_API_SECRET':'synthetic','SCREEN_DISCOVERY_DATA':'true'}
    a=discover(env=env,now=OPEN,fallback=['MU'],session=Session())
    first=set(checked);checked.clear()
    b=discover(env=env,now=OPEN+timedelta(minutes=5),fallback=['MU'],session=Session())
    assert a['discovered_count']==150 and a['screening']['checked']==100
    assert len(first)==100 and len(a['screening']['not_checked'])==50
    assert len(a['selected_symbols'])==19 and not a['fallback_used']
    assert len(first|set(checked))>100
    assert b['screening']['checked']==100
    assert not a['screening']['account_permission_verified']
