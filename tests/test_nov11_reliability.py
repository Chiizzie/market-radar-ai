"""Reproduce stale ledger reads, ambiguous writes and recovered source outages."""
import base64
import json
from copy import deepcopy
from datetime import timedelta
from hashlib import sha1
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from market_radar_ai.agents.github_budget import GitHubBudgetStore, GitHubSpendingLedger, initial_state
from market_radar_ai.agents.openai_pilot import OpenAIPilot
from market_radar_ai.agents.settlement_receipts import reconcile_receipts
from market_radar_ai.agents.watcher_diagnostics import record_failure, record_quote_recovery, recovered_quote_gaps
from market_radar_ai.dashboard.delivery_ledger import DeliveryLedger, GitHubDeliveryStore
from test_spending import NOW
from test_github_budget import MemoryStore
from test_openai_pilot import body, mock_response, SCHEMA


class Remote:
    """A blob server whose GETs may lag, but whose writes enforce current CAS."""
    def __init__(self, state):
        self.state=deepcopy(state); self.reads=[]; self.writes=[]; self.stale=None
        self.sha='a'*40; self.conflict=None; self.lose_ack=False; self.put_status=200

    def get(self, *a, **kw):
        self.reads.append(kw)
        state,sha=self.stale or (self.state,self.sha)
        raw=json.dumps(state).encode()
        return SimpleNamespace(status_code=200,json=lambda:{'encoding':'base64','size':len(raw),
            'sha':sha,'content':base64.b64encode(raw).decode()})

    def put(self,*a,**kw):
        self.writes.append(kw['json'])
        if self.conflict:
            fn,self.conflict=self.conflict,None
            fn(self.state);self.sha='b'*40
            return SimpleNamespace(status_code=409)
        if self.put_status!=200:return SimpleNamespace(status_code=self.put_status)
        if kw['json']['sha']!=self.sha:return SimpleNamespace(status_code=409)
        raw=base64.b64decode(kw['json']['content'])
        self.state=json.loads(raw)
        self.sha=sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if self.lose_ack:raise requests.Timeout('private transport detail')
        return SimpleNamespace(status_code=200)


def remote_budget(monkeypatch, remote):
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.get',remote.get)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put',remote.put)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.time.sleep',lambda _:None)
    return GitHubSpendingLedger(GitHubBudgetStore('offline-token'))


def test_confirmed_reservation_can_settle_despite_stale_get(monkeypatch):
    remote=Remote(initial_state()); ledger=remote_budget(monkeypatch,remote)
    old=deepcopy(remote.state),remote.sha
    ledger.reserve('test',2000,NOW);reserved_sha=remote.sha
    remote.stale=old
    ledger.settle('test',959)
    assert remote.state['entries']['test']['actual']==959
    assert len(remote.reads)==1 and len(remote.writes)==2
    assert remote.writes[1]['sha']==reserved_sha
    assert ledger.summary()['settled_microeur']==959  # Read own settlement.
    with pytest.raises(RuntimeError,match='stale_read'):ledger.summary()
    assert len(remote.reads)==4
    assert len({x['params']['cache_bust'] for x in remote.reads})==4


@pytest.mark.parametrize('other_cost,allowed',[(400000,True),(900000,False)])
def test_definitive_conflict_rechecks_budget_and_preserves_competitor(monkeypatch,other_cost,allowed):
    remote=Remote(initial_state());ledger=remote_budget(monkeypatch,remote)
    remote.conflict=lambda state:state['entries'].update(other={'day':NOW.date().isoformat(),
        'reserved':other_cost,'actual':None,'usage':None})
    if allowed:ledger.reserve('ours',200000,NOW)
    else:
        with pytest.raises(RuntimeError,match='daily_spending_limit'):ledger.reserve('ours',200000,NOW)
    assert ('ours' in remote.state['entries'])==allowed
    assert remote.state['entries']['other']['reserved']==other_cost
    assert len(remote.writes)==(2 if allowed else 1)


@pytest.mark.parametrize('status',[409,500])
def test_only_definitive_conflicts_retry_reservations(monkeypatch,status):
    remote=Remote(initial_state());remote.put_status=status
    ledger=remote_budget(monkeypatch,remote)
    with pytest.raises(RuntimeError):ledger.reserve('ours',200000,NOW)
    assert len(remote.writes)==(3 if status==409 else 1)


def test_lost_reservation_ack_cannot_make_model_call(monkeypatch):
    remote=Remote(initial_state());remote.lose_ack=True
    ledger=remote_budget(monkeypatch,remote);calls=mock_response(monkeypatch,body())
    pilot=OpenAIPilot(api_key='test',ledger=ledger,eur_per_usd='0.9',enabled=True)
    with pytest.raises(RuntimeError,match='unconfirmed'):
        pilot.call(prompt='test',schema=SCHEMA,request_id='paid',now=NOW)
    assert calls==[] and len(remote.writes)==1
    assert remote.state['entries']['paid']['actual'] is None


def test_lost_settlement_ack_is_confirmed_read_only(monkeypatch):
    remote=Remote(initial_state());ledger=remote_budget(monkeypatch,remote)
    ledger.reserve('paid',2000,NOW);remote.lose_ack=True
    ledger.settle('paid',959)
    assert len(remote.writes)==2 and remote.state['entries']['paid']['actual']==959
    assert len(remote.reads)==2


def test_notification_confirmation_uses_acknowledged_reservation():
    remote=Remote({'version':1,'entries':{}})
    ledger=DeliveryLedger(GitHubDeliveryStore('offline',session=remote))
    old=deepcopy(remote.state),remote.sha;key='research:'+'a'*64
    ledger.reserve(key);remote.stale=old;ledger.confirm(key)
    assert remote.state['entries'][key]['state']=='confirmed' and len(remote.reads)==1
    with pytest.raises(ValueError,match='already_attempted'):ledger.reserve(key)


def test_paid_receipt_survives_failed_settlement_and_recovers_without_model_retry(tmp_path,monkeypatch):
    class FailSettlement(MemoryStore):
        fail_settlement=True
        def save(self,state,expected_sha):
            if self.fail_settlement and self.version>=1:raise RuntimeError('unconfirmed settlement')
            super().save(state,expected_sha)
    store=FailSettlement();ledger=GitHubSpendingLedger(store)
    calls=mock_response(monkeypatch,body())
    pilot=OpenAIPilot(api_key='offline',ledger=ledger,eur_per_usd='.9',enabled=True,
                     receipt_directory=tmp_path/'receipts')
    assert pilot.fork().receipt_directory==pilot.receipt_directory
    with pytest.raises(RuntimeError,match='unconfirmed settlement'):
        pilot.call(prompt='test',schema=SCHEMA,request_id='paid',now=NOW)
    files=list((tmp_path/'receipts').glob('*.json'))
    assert len(files)==1 and json.loads(files[0].read_text())['response']==body()
    assert store.state['entries']['paid']['actual'] is None
    store.fail_settlement=False
    result=reconcile_receipts(tmp_path/'receipts',ledger)
    assert result=={'schema_version':'settlement-recovery-v1','model_calls':0,
                    'trade_authorized':False,'reconciled':1,'unresolved':0}
    assert store.state['entries']['paid']['actual']==959 and len(calls)==1
    version=store.version
    assert reconcile_receipts(tmp_path/'receipts',ledger)['reconciled']==1 and store.version==version
    receipt=json.loads(files[0].read_text());receipt['actual_microeur']=0
    files[0].write_text(json.dumps(receipt))
    assert reconcile_receipts(tmp_path/'receipts',ledger)['unresolved']==1 and store.version==version


def test_sent_telegram_is_not_resent_when_confirmation_fails():
    from market_radar_ai.dashboard.collection_notification import notify
    from test_collection_notification import ENV,NOW as NOTICE_NOW
    ledger=Mock();ledger.confirm.side_effect=RuntimeError('ledger offline');session=Mock()
    session.post.return_value=SimpleNamespace(status_code=200,
        json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
    result=notify({},env=ENV,clock=lambda:NOTICE_NOW,ledger=ledger,session=session)
    assert result['state']=='telegram_collection_sent_confirmation_pending'
    assert session.post.call_count==1


def test_status_message_failure_is_visible_optional_warning(monkeypatch,tmp_path,capsys):
    from market_radar_ai.dashboard import collection_notification as notice
    def failed(*a,**k):raise notice.CollectionNoticeError('telegram_transport_unconfirmed')
    monkeypatch.setattr(notice,'notify',failed)
    result=notice.operational_notice({},env={'GITHUB_STEP_SUMMARY':str(tmp_path/'summary')},clock=lambda:NOW)
    assert result['state']=='collection_notice_unconfirmed' and not result['retry_allowed']
    assert '::warning::' in capsys.readouterr().out and 'No automatic resend' in (tmp_path/'summary').read_text()


def healthy_recovery():
    comparison={};record_failure(comparison,'stock_quote_unavailable:TEST:stale_quote',NOW)
    record_quote_recovery(comparison,'TEST',NOW+timedelta(seconds=5))
    return {'comparison':comparison,'polls':20,'error_polls':1,'quotes_received':19,
            'maximum_poll_gap_seconds':5}


def test_small_recovered_quote_gap_can_be_warning():
    assert recovered_quote_gaps(healthy_recovery())


@pytest.mark.parametrize('fault',['unrecovered','many','storage','invalid_quote','capacity','delay','long_gap'])
def test_hard_or_unrecovered_outages_still_fail(fault):
    h=healthy_recovery();c=h['comparison']
    if fault=='unrecovered':record_failure(c,'stock_quote_unavailable:OTHER:missing_quote',NOW)
    if fault=='many':h['error_polls']=5
    if fault=='storage':c['failure_counts']['storage_timeout']=1
    if fault=='invalid_quote':record_failure(c,'stock_quote_unavailable:TEST:crossed_quote',NOW)
    if fault=='capacity':c['capacity_deferred']=1
    if fault=='delay':h['maximum_poll_gap_seconds']=16
    if fault=='long_gap':c['maximum_quote_gap_seconds']=31
    assert not recovered_quote_gaps(h)


def test_recovery_requires_actual_durable_quote_for_same_symbol(tmp_path,monkeypatch):
    from test_comparison_live import environment
    s,p,_,t,_,client=environment(tmp_path,monkeypatch);s.enrol(p,now=t[0])
    original=s.observer.fetch;started=t[0]
    s.observer.fetch=lambda decisions:([],['stock_quote_unavailable:TEST:stale_quote'])
    s.poll();assert s.health['unrecovered_quote_gaps']=={'TEST':t[0].isoformat()}
    t[0]+=timedelta(seconds=5);s.poll()
    assert s.health['unrecovered_quote_gaps']['TEST']==started.isoformat()
    s.observer.fetch=original;t[0]+=timedelta(seconds=5);s.poll()
    assert s.health['unrecovered_quote_gaps']=={} and s.health['maximum_quote_gap_seconds']==10
    assert any(e['kind']=='quote' for e in client.events)


def test_wide_spread_candidate_is_skipped_before_payment_without_starving_next(monkeypatch):
    from test_paper_verdict import fixture
    from market_radar_ai.agents.paper_verdict import choose_unreviewed_packet
    from market_radar_ai.agents.paper_review_prompts import PROMPT_REVISION
    _,p,_,_=fixture(monkeypatch)
    wide=deepcopy(p);wide['packet']['candidate_id']='stocks:WIDE'
    wide['packet']['reference_checks'].update(indicative_bid_eur='100',indicative_ask_eur='101')
    selected,_,_,skipped=choose_unreviewed_packet([wide,p],{},now=NOW)
    assert selected==p and selected['packet']['prompt_revision']==PROMPT_REVISION
    assert skipped==[{'candidate_id':'stocks:WIDE','reason':'reference_spread_exceeds_20bps_before_paid_review'}]


def test_interrupted_review_recovers_cost_into_comparison_without_authorizing_trade(tmp_path,monkeypatch):
    from market_radar_ai.agents import paper_dispatch as dispatch
    from market_radar_ai.agents.settlement_receipts import save_receipt
    from market_radar_ai.agents.openai_pilot import MODEL
    from test_pullback_strategy import synthetic_setup
    doc,feed,now=synthetic_setup();store=MemoryStore();ledger=GitHubSpendingLedger(store)
    ledger.reserve('paid',2000,now)
    comparison=Mock();comparison.sync.return_value=None
    monkeypatch.setattr('market_radar_ai.agents.comparison_live.LiveComparison',lambda *a,**k:comparison)
    monkeypatch.setattr('market_radar_ai.agents.comparison_live.EventClient',lambda *a,**k:None)
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.permitted',lambda *a:True)
    monkeypatch.setattr(dispatch,'refresh_current_inputs',lambda d,**k:(d,{}))
    monkeypatch.setattr(dispatch,'YahooFxProvider',lambda:SimpleNamespace(fetch=lambda *a,**k:SimpleNamespace(eur_per_unit='.9')))
    monkeypatch.setattr(dispatch,'OpenAIPilot',lambda **k:SimpleNamespace(ledger=ledger))
    def interrupted(*a,**kw):
        root=kw['root'];root.mkdir()
        (root/'packet.json').write_text(json.dumps({'packet_id':'audited-original'}))
        save_receipt(root/'provider-receipts',request_id='paid',now=now,actual_microeur=959,
            usage={'response_id':'resp_test','model':MODEL,'input_tokens':1000,'output_tokens':100,
                   'cached_input_tokens':200,'cost_usd':'0.001065','eur_per_usd':'.9','pricing_checked':'2026-11-02'},
            response=body())
        raise RuntimeError('review_interrupted')
    monkeypatch.setattr(dispatch,'run_pipeline',interrupted)
    with pytest.raises(RuntimeError,match='review_interrupted'):
        dispatch.execute(doc,feed,tmp_path/'run',env={'PAPER_FINAL_VERDICTS':'true',
            'PAPER_COMPARISON_ENABLED':'true','GH_BUDGET_TOKEN':'offline'},clock=lambda:now)
    assert store.state['entries']['paid']['actual']==959
    args=comparison.reconcile_cost.call_args.args
    assert args[0]['packet_id']=='audited-original' and args[1]['entries']['paid']['actual']==959
    assert [x[0] for x in comparison.method_calls]==['sync','reconcile_cost','close']
    assert not (tmp_path/'run'/'decision.json').exists()


def test_approved_watcher_records_recovery_without_erasing_missing_quote_history(tmp_path,monkeypatch):
    from market_radar_ai.agents.paper_watcher import run
    from market_radar_ai.agents import github_paper_tracking as journal
    from test_paper_watcher import Clock,ENV,approved,observation
    from test_github_paper_tracking import Session
    from decimal import Decimal
    d=approved(monkeypatch);session=Session();clock=Clock()
    journal.update('offline',now=clock.now(),decision=d,session=session)
    observer=Mock()
    def fetch(decisions):
        if clock.elapsed==0:return [],['stock_quote_unavailable:TEST:stale_quote']
        return [observation(d,clock.now(),Decimal(d['plan']['entry_eur'])-Decimal('.01'))],[]
    observer.fetch.side_effect=fetch
    health=run(env=ENV,output=tmp_path,duration=15,clock=clock.now,
        monotonic=lambda:clock.elapsed,sleep=clock.sleep,observer=observer,session=session)
    assert health['error_polls']==1 and health['state']=='completed_with_gaps'
    assert health['unrecovered_quote_gaps']=={} and health['maximum_quote_gap_seconds']==5
    assert health['quote_gap_counts']=={'TEST':1} and 'TEST' in health['recovered_quote_gap_symbols']
