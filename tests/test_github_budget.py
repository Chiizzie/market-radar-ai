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
    GitHubSpendingLedger(store).reserve('one',600000,NOW)
    fresh=GitHubSpendingLedger(store)
    with pytest.raises(RuntimeError): fresh.reserve('two',600000,NOW)
    with pytest.raises(ValueError): fresh.reserve('one',1,NOW)
    fresh.settle('one',100)
    fresh.reserve('two',600000,NOW)
    assert fresh.summary()['held_microeur']==600000
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
    store.state['entries']['older']={'day':'2026-10-01','reserved':99000000,'actual':99000000,'usage':None}
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
    state=initial_state();state['limits_microeur']['lifetime']=101000000
    with pytest.raises(ValueError): validate_state(state)


def test_overrun_and_idempotent_settlement():
    store=MemoryStore();ledger=GitHubSpendingLedger(store)
    ledger.reserve('one',1,NOW)
    with pytest.raises(RuntimeError,match='actual_charge_recorded'): ledger.settle('one',1000001)
    ledger.settle('one',1000001)
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
    monkeypatch.setattr('market_radar_ai.agents.github_budget.time.sleep',lambda _:None)
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


@pytest.mark.parametrize('first', ['timeout', 429, 500, 502, 503, 504])
def test_transient_read_retries_without_writes_and_preserves_existing_holds(monkeypatch,first):
    import base64,json,requests
    from types import SimpleNamespace
    state=initial_state();state['entries']['held']={'day':'2026-11-06','reserved':100,'actual':None,'usage':None}
    good=SimpleNamespace(status_code=200,json=lambda:{'sha':'b'*40,'size':400,'encoding':'base64',
        'content':base64.b64encode(json.dumps(state).encode()).decode()})
    calls=[];waits=[]
    def get(*a,**k):
        calls.append(k)
        if len(calls)==1:
            if first=='timeout':raise requests.Timeout('secret provider details')
            return SimpleNamespace(status_code=first,headers={})
        return good
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.get',get)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.time.sleep',waits.append)
    def forbidden(*a,**k):raise AssertionError('read recovery must never write')
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put',forbidden)
    loaded,sha=GitHubBudgetStore('secret').load()
    assert loaded==state and sha=='b'*40 and len(calls)==2 and waits==[1]
    assert all(c['allow_redirects'] is False and c['params']['ref']==BRANCH
               and c['headers']['Cache-Control']=='no-cache' for c in calls)
    assert len({c['params']['cache_bust'] for c in calls})==2


@pytest.mark.parametrize('code,headers,expected', [(401,{},1),(403,{},1),(404,{},1),(302,{},1),
    (429,{'Retry-After':'60'},1),(403,{'Retry-After':'1'},3),(503,{},3)])
def test_read_retry_bound_and_permanent_errors_are_fail_closed(monkeypatch,code,headers,expected):
    from types import SimpleNamespace
    calls=[]
    def get(*a,**k):calls.append(1);return SimpleNamespace(status_code=code,headers=headers)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.get',get)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.time.sleep',lambda _:None)
    with pytest.raises(RuntimeError,match=f'http_{code}') as e:GitHubBudgetStore('SECRET').load()
    assert len(calls)==expected and 'SECRET' not in str(e.value)


def test_corrupt_successful_response_is_not_retried(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    def get(*a,**k):calls.append(1);return SimpleNamespace(status_code=200,json=lambda:{'encoding':'wrong'})
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.get',get)
    with pytest.raises(RuntimeError,match='invalid_payload'):GitHubBudgetStore('secret').load()
    assert len(calls)==1


@pytest.mark.parametrize(('stamp', 'monthly'), [
    ('2026-11-23T20:12:38.999999+00:00', 10_000_000),
    ('2026-11-23T20:12:39+00:00', 25_000_000),
    ('2026-12-01T00:59:59.999999+01:00', 25_000_000),
    ('2026-11-30T19:00:00-05:00', 10_000_000),
    ('2027-11-23T20:12:39+00:00', 10_000_000),
])
def test_time_scoped_budget_is_consistent_in_reports(stamp, monthly):
    from market_radar_ai.dashboard.api_budget import summarize
    now = datetime.fromisoformat(stamp)
    store = MemoryStore()
    ledger = GitHubSpendingLedger(store)
    expected = {'daily': 1_000_000, 'monthly': monthly, 'lifetime': 100_000_000}
    assert ledger.summary(now=now)['limits_microeur'] == expected
    assert {name: period['limit_microeur'] for name, period in
            summarize(store.state, now=now)['periods'].items()} == expected
    assert store.state['limits_microeur']['monthly'] == 10_000_000


def test_november_increase_preserves_holds_and_enforces_each_period():
    from market_radar_ai.agents.scheduled_review import claim_review
    from market_radar_ai.dashboard.api_budget import summarize

    store = MemoryStore()
    ledger = GitHubSpendingLedger(store)
    store.state['entries'] = {
        'older': {'day': '2026-10-18', 'reserved': 74_900_000, 'actual': 74_900_000, 'usage': None},
        'settled': {'day': '2026-11-10', 'reserved': 9_800_000, 'actual': 9_800_000, 'usage': None},
        'unsettled': {'day': '2026-11-11', 'reserved': 200_000, 'actual': None, 'usage': None},
    }
    start = datetime.fromisoformat('2026-11-23T20:12:39+00:00')
    previous = start.replace(second=38)
    assert not claim_review(store, 'stocks', previous)
    with pytest.raises(RuntimeError, match='monthly_spending_limit'):
        ledger.reserve('before', 1, previous)
    assert claim_review(store, 'stocks', start)
    assert summarize(store.state, now=start)['periods']['monthly']['remaining_microeur'] == 15_000_000
    ledger.reserve('today', 1_000_000, start)
    with pytest.raises(RuntimeError, match='daily_spending_limit'):
        ledger.reserve('daily-block', 1, start)

    # A near-limit ledger exercises a restart at the monthly boundary.
    store.state['entries']['month-spend'] = {
        'day': '2026-11-25', 'reserved': 13_900_000, 'actual': 13_900_000, 'usage': None}
    last_day = datetime.fromisoformat('2026-11-30T23:59:59+00:00')
    assert not claim_review(store, 'stocks', last_day)  # €0.10 below review reserve.
    ledger = GitHubSpendingLedger(store)
    ledger.reserve('last', 100_000, last_day)
    with pytest.raises(RuntimeError, match='monthly_spending_limit'):
        ledger.reserve('monthly-block', 1, last_day)
    december = datetime.fromisoformat('2026-12-01T00:00:00+00:00')
    assert summarize(store.state, now=december)['periods']['monthly']['remaining_microeur'] == 10_000_000
    ledger.reserve('next-month', 100_000, december)
    with pytest.raises(RuntimeError, match='lifetime_spending_limit'):
        ledger.reserve('lifetime-block', 1, december)
    assert store.state['entries']['unsettled']['actual'] is None
    assert store.state['limits_microeur'] == initial_state()['limits_microeur']
