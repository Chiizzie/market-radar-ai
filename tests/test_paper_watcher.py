"""Synthetic market clock and quotes; no models, real accounts or Telegram sends."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock
import pytest
import requests
from test_github_paper_tracking import Session
from test_paper_verdict import fixture,NOW
from test_scheduled_collection import ENV as COLLECTION_ENV
from market_radar_ai.agents.paper_verdict import finalize
from market_radar_ai.agents.paper_tracking import PaperTracker
from market_radar_ai.agents.paper_outcomes import Quote
from market_radar_ai.agents import github_paper_tracking as journal
from market_radar_ai.agents.paper_watcher import poll_once,run

ENV={**COLLECTION_ENV,'GH_PAPER_TOKEN':'fake'}

class Clock:
    def __init__(self):self.elapsed=0
    def now(self):return NOW+timedelta(seconds=self.elapsed)
    def sleep(self,seconds):self.elapsed+=seconds

def approved(monkeypatch):
    _,packet,audit,_=fixture(monkeypatch)
    return finalize(packet,audit,{},None,now=NOW)

def observation(d,at,value):
    return {'packet_id':d['packet_id'],'symbol':d['plan']['symbol'],'source':'synthetic',
            'quote':Quote(observed_at=at,bid=value,ask=value).model_dump(mode='json')}

def test_entry_within_seconds_survives_restart_and_records_target(monkeypatch):
    d=approved(monkeypatch);s=Session();c=Clock();p=d['plan']
    journal.update('fake',now=NOW,decision=d,session=s)
    observer=Mock()
    observer.fetch.side_effect=lambda ds:([observation(d,c.now(),p['entry_eur'])],[])
    c.elapsed=5
    first=poll_once(env=ENV,observer=observer,clock=c.now,session=s)
    assert first['report']['trades'][0]['state']=='open_simulation'
    # Another process sees the persisted entry, with no duplicate fill/write.
    poll_once(env=ENV,observer=observer,clock=c.now,session=s)
    assert s.writes==2
    c.elapsed=10;observer.fetch.side_effect=lambda ds:([observation(d,c.now(),p['target_eur'])],[])
    last=poll_once(env=ENV,observer=observer,clock=c.now,session=s)
    outcome=last['report']['trades'][0]['outcome']
    assert outcome['status']=='closed' and outcome['reason']=='target'
    assert Decimal(outcome['net_pnl_eur'])==(Decimal(p['target_eur'])-Decimal(p['entry_eur']))*Decimal(p['quantity'])-Decimal(p['assumed_round_trip_cost_eur'])
    assert len(s.state['observations'])==2 and s.writes==3

def test_five_minute_poll_still_cannot_backdate_an_entry(monkeypatch):
    d=approved(monkeypatch);s=Session();journal.update('fake',now=NOW,decision=d,session=s)
    observer=Mock();clock=lambda:NOW+timedelta(minutes=5)
    r=poll_once(env=ENV,observer=observer,clock=clock,session=s)
    observer.fetch.assert_not_called()
    assert r['report']['trades'][0]['outcome']['net_pnl_eur'] is None

def test_nonexact_quote_before_deadline_closes_but_late_quote_does_not(monkeypatch,tmp_path):
    from datetime import datetime
    d=approved(monkeypatch);p=d['plan'];end=datetime.fromisoformat(p['exit_by'])
    for name,at,expected in [('before',end-timedelta(seconds=17),'closed'),('after',end+timedelta(seconds=1),'unresolved')]:
        t=PaperTracker(tmp_path/name);key=t.register(d)
        t.observe_transition(key,Quote(observed_at=NOW+timedelta(seconds=5),bid=p['entry_eur'],ask=p['entry_eur']),symbol='TEST',source='synthetic',now=NOW+timedelta(seconds=5))
        t.observe_transition(key,Quote(observed_at=at,bid=p['entry_eur'],ask=p['entry_eur']),symbol='TEST',source='synthetic',now=at)
        o=t.report(now=end+timedelta(seconds=2))['trades'][0]['outcome']
        assert o['status']==expected
        assert o['reason']==('scheduled_exit' if expected=='closed' else 'no_observed_exit_by_deadline')
        if expected=='closed':assert o['exit_at']==at.isoformat().replace('+00:00','Z')
        else:assert o['net_pnl_eur'] is None

def test_stable_polls_do_not_grow_git_journal(monkeypatch):
    d=approved(monkeypatch);s=Session();journal.update('fake',now=NOW,decision=d,session=s)
    for second in range(1,20):
        journal.update('fake',now=NOW+timedelta(seconds=second),session=s,
            observations=[observation(d,NOW+timedelta(seconds=second),Decimal(d['plan']['entry_eur'])-Decimal('.1'))])
    assert s.writes==1 and s.state['observations']==[]

def test_conflict_merges_other_registered_plan_without_overwrite(monkeypatch):
    d=approved(monkeypatch);other=deepcopy(d);other['packet_id']='b'*64
    other['candidate_id']='stocks:OTHER';other['plan']['symbol']='OTHER'
    class Conflict(Session):
        def put(self,url,**kw):
            if self.writes==0:
                self.writes+=1;self.state['decisions'].append(other)
                return Mock(status_code=409)
            return super().put(url,**kw)
    s=Conflict();r=journal.update('fake',now=NOW,decision=d,session=s)
    assert {x['symbol'] for x in r['trades']}=={'TEST','OTHER'}
    assert len(s.state['decisions'])==2

def test_unknown_write_acknowledgement_is_reconciled_on_next_read(monkeypatch):
    d=approved(monkeypatch)
    class LostAck(Session):
        def put(self,*a,**kw):
            super().put(*a,**kw)
            raise requests.ConnectionError('private detail')
    s=LostAck()
    with pytest.raises(RuntimeError,match='unconfirmed'):journal.update('fake',now=NOW,decision=d,session=s)
    assert journal.update('fake',now=NOW,decision=d,session=s)['trades'][0]['state']=='watching'
    assert s.writes==1

def test_idle_watcher_reads_only_every_fifteen_seconds(tmp_path):
    class Count(Session):
        def __init__(self):super().__init__();self.reads=0
        def get(self,*a,**kw):self.reads+=1;return super().get(*a,**kw)
    s=Count();c=Clock();observer=Mock()
    status=run(env=ENV,output=tmp_path,duration=30,clock=c.now,monotonic=lambda:c.elapsed,sleep=c.sleep,observer=observer,session=s)
    assert status['polls']==6 and status['maximum_poll_gap_seconds']==5
    assert s.reads==2 and s.writes==0 and status['model_calls']==0
    observer.fetch.assert_not_called()

def test_missing_comparison_secret_preserves_existing_approved_watcher(tmp_path):
    s=Session();c=Clock();observer=Mock()
    status=run(env={**ENV,'PAPER_COMPARISON_ENABLED':'true','REVIEW_INGEST_SECRET':''},output=tmp_path,duration=10,
               clock=c.now,monotonic=lambda:c.elapsed,sleep=c.sleep,observer=observer,session=s)
    assert status['polls']==2 and 'comparison_state' not in status

def test_weekends_and_paid_credentials_never_observe(tmp_path):
    c=Clock();observer=Mock();s=Session()
    result=run(env=ENV,output=tmp_path,clock=lambda:NOW+timedelta(days=5),observer=observer,session=s)
    assert result['state']=='outside_window'
    with pytest.raises(ValueError,match='paid_credentials'):
        run(env={**ENV,'OPENAI_API_KEY':'forbidden'},output=tmp_path,observer=observer,session=s)
    observer.fetch.assert_not_called()

def test_provider_gap_preserves_unknown_outcome(monkeypatch,tmp_path):
    d=approved(monkeypatch);s=Session();journal.update('fake',now=NOW,decision=d,session=s)
    observer=Mock();observer.fetch.return_value=([],['crypto_reference_observation_unavailable']);c=Clock()
    status=run(env=ENV,output=tmp_path,duration=15,clock=c.now,monotonic=lambda:c.elapsed,sleep=c.sleep,observer=observer,session=s)
    assert status['state']=='completed_with_gaps' and status['error_polls']==3
    assert s.state['observations']==[]

def test_exit_window_never_opens_a_new_paper_position(monkeypatch,tmp_path):
    from datetime import datetime
    d=approved(monkeypatch);end=datetime.fromisoformat(d['plan']['exit_by'])
    d['plan']['expires_at']=end.isoformat()
    t=PaperTracker(tmp_path/'journal');key=t.register(d)
    at=end-timedelta(seconds=20)
    t.observe_transition(key,Quote(observed_at=at,bid=d['plan']['entry_eur'],ask=d['plan']['entry_eur']),symbol='TEST',source='synthetic',now=at)
    assert t.report(now=end)['trades'][0]['outcome']['entry_at'] is None
