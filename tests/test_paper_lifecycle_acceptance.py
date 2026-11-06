"""Full production adapters with synthetic evidence/model/HTTP responses only."""
from copy import deepcopy
from datetime import datetime,timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
from test_opening_and_crypto import crypto_document,news,NOW
from test_github_budget import MemoryStore
from test_github_paper_tracking import Session
from test_paper_watcher import ENV,Clock
from market_radar_ai.agents.openai_pilot import OpenAIPilot
from market_radar_ai.agents.github_budget import GitHubSpendingLedger
from market_radar_ai.agents.paper_verdict import run_pipeline,STAGES
from market_radar_ai.agents.paper_watcher import poll_once
from market_radar_ai.agents.paper_observer import ReferenceObserver
from market_radar_ai.agents import github_paper_tracking as journal
from market_radar_ai.market_data.reference_quotes import digest
from market_radar_ai.dashboard.diagnostics import TrackingReport
from market_radar_ai.dashboard.paper_lifecycle_delivery import notify

@pytest.mark.parametrize('case',['target','stop_gap','scheduled_exit','missing_exit'])
def test_evidence_to_eight_reviews_to_persistent_observed_outcome(tmp_path,monkeypatch,case):
    doc=crypto_document();feed=news();s=Session();clock=Clock();stages=[];archives=[]
    client=OpenAIPilot(api_key='synthetic',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='.9',enabled=True)
    def call(**kw):
        prompt=json.loads(kw['prompt']);stages.append(prompt['stage'])
        return SimpleNamespace(data={'verdict':'APPROVE_PAPER','rationale':'Synthetic acceptance only',
            'source_ids':[prompt['packet']['source_ids'][0]],'concerns':[]})
    monkeypatch.setattr(client,'call',call)
    value=[None]
    def quote_feed(*a,**kw):
        capture=deepcopy(doc['reference_quote_capture'])
        capture['request_started_at']=capture['retrieved_at']=clock.now().isoformat()
        if value[0] is not None:
            ticker=next(iter(capture['payload']['tickers']['result'].values()))
            ticker['a'][0]=ticker['b'][0]=str(value[0])
        capture['payload_sha256']=digest(capture['payload'])
        return capture
    observer=ReferenceObserver({},clock=clock.now,crypto_fetch=quote_feed)
    def deliver(archive):
        archives.append(archive)
        journal.update('fake',now=clock.now(),decision=archive['decision'],session=s)
        first=poll_once(env=ENV,observer=observer,clock=clock.now,session=s)
        assert first['report']['trades'][0]['state']=='watching'
        return {'state':'synthetic_dashboard_acknowledgement'}
    result=run_pipeline(doc,feed,client=client,root=tmp_path/'attempt',refresh=lambda symbol:(doc,feed),
                        deliver=deliver,clock=clock.now,enabled=True)
    assert result['verdict']=='PAPER_WATCH_FOR_ENTRY' and stages==STAGES and len(archives)==1
    p=archives[0]['decision']['plan'];value[0]=p['entry_eur'];clock.elapsed=5
    opened=poll_once(env=ENV,observer=observer,clock=clock.now,session=s)['report']
    assert TrackingReport.model_validate(opened).trades[0].state=='open_simulation'
    if case=='scheduled_exit':
        clock.elapsed=(datetime.fromisoformat(p['exit_by'])-NOW).total_seconds()-17
    elif case=='missing_exit':
        clock.elapsed=(datetime.fromisoformat(p['exit_by'])-NOW).total_seconds()+1
    else:
        clock.elapsed=10
        value[0]=p['target_eur'] if case=='target' else Decimal(p['stop_eur'])-Decimal('.01')
    finished=poll_once(env=ENV,observer=observer,clock=clock.now,session=s)['report']
    validated=TrackingReport.model_validate(finished);row=finished['trades'][0]
    if case=='missing_exit':
        assert row['state']=='unresolved' and row['outcome']['net_pnl_eur'] is None
    else:
        assert row['state']=='closed'
        assert row['outcome']['reason']==('stop' if case=='stop_gap' else case)
        expected=(Decimal(str(value[0]))-Decimal(p['entry_eur']))*Decimal(p['quantity'])-Decimal(p['assumed_round_trip_cost_eur'])
        assert Decimal(row['outcome']['net_pnl_eur'])==expected
        assert len(s.state['observations'])==2
    transport=Mock();transport.post.return_value=Mock(status_code=200,json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
    notification=notify(finished,env={**ENV,'SEND_PAPER_LIFECYCLE_TELEGRAM':'true','TELEGRAM_BOT_TOKEN':'synthetic','TELEGRAM_CHAT_ID':'123'},
        now=clock.now(),ledger=Mock(),session=transport)
    assert notification['sent']==1 and validated.trade_authorized is False
    assert not archives[0]['decision']['live_orders_enabled']
