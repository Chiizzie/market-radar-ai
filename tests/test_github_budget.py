from copy import deepcopy
from datetime import datetime, timezone
import pytest
from market_radar_ai.agents.github_budget import (
    GitHubSpendingLedger, GitHubBudgetStore, initial_state, validate_state, BRANCH, URL)
from test_spending import NOW


class MemoryStore:
    def __init__(self):
        self.state, self.version = initial_state(), 0
        self.fail_write = False
    def load(self): return deepcopy(self.state), self.version
    def save(self, state, expected_sha):
        if self.fail_write or expected_sha != self.version:
            raise RuntimeError('unconfirmed write')
        self.state=deepcopy(validate_state(state))
        self.version += 1


def test_restarts_keep_holds_and_duplicate_ids():
    store=MemoryStore()
    GitHubSpendingLedger(store).reserve('one',300000,NOW)
    fresh=GitHubSpendingLedger(store)
    with pytest.raises(RuntimeError): fresh.reserve('two',300000,NOW)
    with pytest.raises(ValueError): fresh.reserve('one',1,NOW)
    fresh.settle('one',100)
    fresh.reserve('two',300000,NOW)
    assert fresh.summary()['held_microeur']==300000
    assert fresh.summary()['settled_microeur']==100


def test_conflict_cannot_overwrite_reservation():
    store=MemoryStore()
    stale, version=store.load()
    GitHubSpendingLedger(store).reserve('winner',300000,NOW)
    with pytest.raises(RuntimeError): store.save(stale,version)
    assert 'winner' in store.state['entries']


def test_lifetime_survives_month_boundary():
    store=MemoryStore()
    ledger=GitHubSpendingLedger(store)
    ledger.reserve('one',400000,NOW)
    ledger.reserve('two',400000,NOW.replace(month=12))
    with pytest.raises(RuntimeError,match='lifetime'):
        ledger.reserve('three',200001,NOW.replace(year=2027,month=1))


def test_unknown_write_blocks_pilot_before_network(tmp_path,monkeypatch):
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    store=MemoryStore();store.fail_write=True
    pilot=OpenAIPilot(api_key='test',ledger=GitHubSpendingLedger(store),eur_per_usd=1,enabled=True)
    def forbidden(*args, **kwargs): pytest.fail('Provider must not be contacted')
    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post',forbidden)
    with pytest.raises(RuntimeError):
        pilot.call(prompt='test',schema={'type':'object','properties':{}},request_id='x',now=NOW)


def test_corrupt_limits_are_not_silently_reset():
    state=initial_state();state['limits_microeur']['lifetime']=100000000
    with pytest.raises(ValueError): validate_state(state)


def test_overrun_and_idempotent_settlement():
    store=MemoryStore();ledger=GitHubSpendingLedger(store)
    ledger.reserve('one',1,NOW)
    with pytest.raises(RuntimeError,match='actual_charge_recorded'): ledger.settle('one',500001)
    ledger.settle('one',500001)
    with pytest.raises(ValueError): ledger.settle('one',1)
    with pytest.raises(RuntimeError): ledger.reserve('two',1,NOW)


def test_remote_write_uses_only_designated_state_branch(monkeypatch):
    calls=[]
    class Response: status_code=200
    def put(*args,**kwargs): calls.append((args,kwargs));return Response()
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put',put)
    GitHubBudgetStore('not-a-real-token').save(initial_state(),'a'*40)
    args,kwargs=calls[0]
    assert args==(URL,) and kwargs['json']['branch']==BRANCH
    assert kwargs['json']['sha']=='a'*40 and kwargs['allow_redirects'] is False


@pytest.mark.parametrize('code',[403,404,409,500])
def test_remote_read_failure_does_not_initialize(monkeypatch,code):
    class Response: status_code=code
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.get',lambda *a,**k:Response())
    with pytest.raises(RuntimeError,match='read failed'): GitHubBudgetStore('test').load()


def test_storage_probe_replays_without_more_writes():
    from market_radar_ai.agents.github_pilot import storage_check
    store=MemoryStore()
    first=storage_check(store,NOW)
    version=store.version
    assert storage_check(store,NOW)==first and store.version==version
    assert first['settled_microeur']==0 and first['held_microeur']==0


def test_existing_connectivity_attempt_never_repeats():
    from market_radar_ai.agents.github_pilot import connectivity_check
    store=MemoryStore()
    GitHubSpendingLedger(store).reserve('openai-connectivity-v1',300000,NOW)
    result=connectivity_check(store,key='',now=NOW)
    assert result['status']=='already_attempted_no_retry'


def test_remote_pilot_settles_usage_in_same_state_write(monkeypatch):
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from test_openai_pilot import mock_response, body, SCHEMA
    store=MemoryStore()
    pilot=OpenAIPilot(api_key='test',ledger=GitHubSpendingLedger(store),eur_per_usd='0.9',enabled=True)
    mock_response(monkeypatch,body())
    result=pilot.call(prompt='test',schema=SCHEMA,request_id='paid-test',now=NOW)
    row=store.state['entries']['paid-test']
    assert row['actual']==959 and row['usage']['cost_usd']=='0.001065'
    assert store.version==2


def test_lost_write_acknowledgement_blocks_call_and_later_retry(monkeypatch):
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    class LostAckStore(MemoryStore):
        def save(self,state,expected_sha):
            super().save(state,expected_sha)
            raise RuntimeError('reply lost after successful write')
    store=LostAckStore()
    pilot=OpenAIPilot(api_key='test',ledger=GitHubSpendingLedger(store),eur_per_usd=1,enabled=True)
    def forbidden(*args, **kwargs): pytest.fail('No paid request after ambiguous storage write')
    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post',forbidden)
    with pytest.raises(RuntimeError):
        pilot.call(prompt='test',schema={'type':'object','properties':{}},request_id='x',now=NOW)
    with pytest.raises(ValueError,match='already reserved'):
        pilot.call(prompt='test',schema={'type':'object','properties':{}},request_id='x',now=NOW)
    assert store.state['entries']['x']['actual'] is None


def test_failed_remote_settlement_retains_full_hold(monkeypatch):
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from test_openai_pilot import mock_response,body,SCHEMA
    class SettlementFailure(MemoryStore):
        def save(self,state,expected_sha):
            if self.version==1: raise RuntimeError('settlement failed')
            super().save(state,expected_sha)
    store=SettlementFailure()
    pilot=OpenAIPilot(api_key='test',ledger=GitHubSpendingLedger(store),eur_per_usd=1,enabled=True)
    mock_response(monkeypatch,body())
    with pytest.raises(RuntimeError,match='settlement failed'):
        pilot.call(prompt='test',schema=SCHEMA,request_id='x',now=NOW)
    row=store.state['entries']['x']
    assert row['actual'] is None and row['reserved'] > 300000


def test_remote_record_round_trip(monkeypatch):
    import base64,json
    class Response:
        status_code=200
        def json(self):
            return {'sha':'a'*40,'size':200,'encoding':'base64',
                    'content':base64.b64encode(json.dumps(initial_state()).encode()).decode()}
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.get',lambda *a,**k:Response())
    state,sha=GitHubBudgetStore('test').load()
    assert state==initial_state() and sha=='a'*40
