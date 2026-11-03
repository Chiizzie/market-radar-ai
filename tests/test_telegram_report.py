from datetime import datetime, timezone
import pytest
from market_radar_ai.dashboard.telegram_report import execute
from market_radar_ai.dashboard.delivery_ledger import DeliveryLedger
from test_delivery_ledger import Store

ENV = dict(GITHUB_REPOSITORY='Chiizzie/market-radar-ai',
    GITHUB_REF='refs/heads/phase-1/market-data-layer',
    GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ATTEMPT='1',
    SEND_HISTORICAL_REPORT='true', TELEGRAM_BOT_TOKEN='SECRET', TELEGRAM_CHAT_ID='123')
NOW = datetime(2026, 11, 3, 21, tzinfo=timezone.utc)

class Session:
    def __init__(self, store, fault=None):
        self.store = store; self.fault = fault; self.calls = 0
    def post(self, url, **kw):
        self.calls += 1
        assert list(self.store.state['entries'].values()) == [{'state': 'reserved'}]
        assert kw['allow_redirects'] is False
        assert 'EXPIRED' in kw['json']['text'] and 'NOT A TRADE CALL' in kw['json']['text']
        assert 'parse_mode' not in kw['json']
        if self.fault == 'timeout': raise TimeoutError('SECRET')
        class Response:
            status_code = 200
            def json(inner):
                return {'ok': True, 'result': {'chat': {'id': 999 if self.fault else 123}, 'message_id': 1}}
        return Response()


def test_delivery_then_restart_cannot_duplicate():
    store = Store(); session = Session(store)
    result = execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session)
    assert result['state'] == 'historical_report_delivery_confirmed'
    with pytest.raises(ValueError):
        execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session)
    assert session.calls == 1

@pytest.mark.parametrize('fault', ['timeout', 'wrong_destination'])
def test_uncertain_delivery_permanently_blocks_retry(fault):
    store = Store(); session = Session(store, fault)
    with pytest.raises(RuntimeError) as error:
        execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session)
    assert 'SECRET' not in str(error.value)
    with pytest.raises(ValueError):
        execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session)
    assert session.calls == 1

@pytest.mark.parametrize('key,value', [('GITHUB_RUN_ATTEMPT','2'),
    ('GITHUB_EVENT_NAME','push'), ('SEND_HISTORICAL_REPORT','false'),
    ('GITHUB_REPOSITORY','Chiizzie/market-radar'), ('GITHUB_REF','refs/heads/main')])
def test_manual_scope_required(key, value):
    store = Store(); session = Session(store)
    with pytest.raises(ValueError):
        execute({**ENV, key:value}, ledger=DeliveryLedger(store), now=NOW, session=session)
    assert session.calls == 0 and not store.state['entries']


def test_tampered_report_never_reserved_or_sent():
    store = Store(); session = Session(store)
    with pytest.raises(ValueError, match='untrusted_report'):
        execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session, report_bytes=b'{}')
    assert session.calls == 0 and not store.state['entries']


def test_failed_reservation_never_posts():
    store = Store(); session = Session(store)
    def fail(*args): raise RuntimeError('write uncertain')
    store.save = fail
    with pytest.raises(RuntimeError):
        execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session)
    assert session.calls == 0


def test_failed_confirmation_never_resends():
    store = Store(); session = Session(store)
    save = store.save
    def fail_confirmation(state, sha):
        if sha == 1: raise RuntimeError('uncertain')
        save(state, sha)
    store.save = fail_confirmation
    with pytest.raises(RuntimeError):
        execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session)
    with pytest.raises(ValueError):
        execute(ENV, ledger=DeliveryLedger(store), now=NOW, session=session)
    assert session.calls == 1
