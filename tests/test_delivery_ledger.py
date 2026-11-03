import copy
import pytest
from market_radar_ai.dashboard.delivery_ledger import (
    DeliveryLedger, GitHubDeliveryStore, initial_state, validate, BRANCH, URL)

KEY = 'research:' + 'a' * 64

class Store:
    def __init__(self):
        self.state = initial_state()
        self.revision = 0
    def load(self):
        return copy.deepcopy(self.state), self.revision
    def save(self, state, sha):
        if sha != self.revision:
            raise RuntimeError('conflict')
        self.state = copy.deepcopy(state)
        self.revision += 1


def test_reserved_attempt_stays_blocked_after_restart():
    store = Store()
    DeliveryLedger(store).reserve(KEY)
    with pytest.raises(ValueError, match='already_attempted'):
        DeliveryLedger(store).reserve(KEY)


def test_confirmation_is_idempotent_and_cannot_be_resent():
    store = Store(); ledger = DeliveryLedger(store)
    ledger.reserve(KEY); ledger.confirm(KEY); ledger.confirm(KEY)
    assert store.revision == 2
    assert store.state['entries'][KEY]['state'] == 'confirmed'
    with pytest.raises(ValueError): ledger.reserve(KEY)


def test_confirm_requires_reservation():
    with pytest.raises(ValueError): DeliveryLedger(Store()).confirm(KEY)


def test_concurrent_stale_writer_loses():
    store = Store()
    stale, revision = store.load()
    DeliveryLedger(store).reserve(KEY)
    stale['entries'][KEY] = {'state': 'reserved'}
    with pytest.raises(RuntimeError): store.save(stale, revision)


@pytest.mark.parametrize('raw', [None, {}, {'version': True, 'entries': {}},
    {'version': 1, 'entries': {KEY: {'state': 'retry'}}},
    {'version': 1, 'entries': {'bad': {'state': 'reserved'}}}])
def test_corrupt_ledger_rejected(raw):
    with pytest.raises(ValueError): validate(raw)


class Response:
    status_code = 409

class Session:
    def put(self, url, **kwargs):
        assert url == URL
        assert kwargs['json']['branch'] == BRANCH
        assert kwargs['json']['sha'] == 'b' * 40
        assert kwargs['allow_redirects'] is False
        return Response()
    def get(self, url, **kwargs):
        raise RuntimeError('SECRET')


def test_conflict_does_not_retry():
    with pytest.raises(RuntimeError, match='do not send or retry'):
        GitHubDeliveryStore('SECRET', session=Session()).save(initial_state(), 'b'*40)


def test_missing_store_does_not_initialize_or_leak_secret():
    with pytest.raises(RuntimeError) as error:
        GitHubDeliveryStore('SECRET', session=Session()).load()
    assert 'SECRET' not in str(error.value)
