from datetime import timedelta
import pytest
from test_review_export import bundle, NOW
from test_delivery_ledger import Store
from market_radar_ai.dashboard.delivery_ledger import DeliveryLedger
from market_radar_ai.dashboard.fresh_notification import deliver

ENV = dict(GITHUB_REPOSITORY='Chiizzie/market-radar-ai',
    GITHUB_REF='refs/heads/phase-1/market-data-layer', GITHUB_EVENT_NAME='workflow_dispatch',
    GITHUB_RUN_ATTEMPT='1', PLAN_REVIEW_MODE='paid', SEND_FRESH_REVIEW='true',
    TELEGRAM_BOT_TOKEN='SECRET', TELEGRAM_CHAT_ID='123')

class Session:
    def __init__(self, store, fail=False): self.store=store; self.calls=0; self.fail=fail
    def post(self, url, **kwargs):
        self.calls+=1
        assert list(self.store.state['entries'].values()) == [{'state':'reserved'}]
        assert 'NOT A TRADE CALL' in kwargs['json']['text']
        assert 'EXPIRED' not in kwargs['json']['text']
        assert kwargs['allow_redirects'] is False
        if self.fail: raise TimeoutError('SECRET')
        class Response:
            status_code=200
            def json(self):return {'ok':True,'result':{'chat':{'id':123},'message_id':7}}
        return Response()


def test_validated_fresh_review_delivered_once():
    b=bundle(); store=Store(); session=Session(store)
    result=deliver(*b, env=ENV, ledger=DeliveryLedger(store), clock=lambda:NOW, session=session)
    assert result['state']=='fresh_research_delivery_confirmed' and not result['trade_authorized']
    with pytest.raises(ValueError):
        deliver(*b, env=ENV, ledger=DeliveryLedger(store), clock=lambda:NOW, session=session)
    assert session.calls==1

@pytest.mark.parametrize('seconds',[121,300,3600])
def test_old_review_never_reserved(seconds):
    store=Store(); session=Session(store)
    with pytest.raises(ValueError):
        deliver(*bundle(), env=ENV, ledger=DeliveryLedger(store), clock=lambda:NOW+timedelta(seconds=seconds), session=session)
    assert not store.state['entries'] and session.calls==0


def test_reservation_delay_blocks_send_but_retains_identity():
    store=Store(); session=Session(store); times=iter([NOW,NOW+timedelta(minutes=5)])
    with pytest.raises(ValueError):
        deliver(*bundle(), env=ENV, ledger=DeliveryLedger(store), clock=lambda:next(times), session=session)
    assert session.calls==0 and list(store.state['entries'].values())==[{'state':'reserved'}]


def test_tampered_audit_rejected_before_reservation():
    b=bundle(); b[3]['calls'][0]['untrusted_response']['rationale']='bad'
    store=Store(); session=Session(store)
    with pytest.raises(ValueError):
        deliver(*b, env=ENV, ledger=DeliveryLedger(store), clock=lambda:NOW, session=session)
    assert not store.state['entries'] and session.calls==0


def test_timeout_has_no_retry_or_secret():
    store=Store(); session=Session(store, True)
    with pytest.raises(RuntimeError) as error:
        deliver(*bundle(), env=ENV, ledger=DeliveryLedger(store), clock=lambda:NOW, session=session)
    assert 'SECRET' not in str(error.value)
    with pytest.raises(ValueError):
        deliver(*bundle(), env=ENV, ledger=DeliveryLedger(store), clock=lambda:NOW, session=session)
    assert session.calls==1

@pytest.mark.parametrize('key,value',[('SEND_FRESH_REVIEW','false'),('PLAN_REVIEW_MODE','dry_run'),
    ('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','schedule'),('GITHUB_REPOSITORY','Chiizzie/market-radar')])
def test_explicit_scope(key,value):
    store=Store(); session=Session(store)
    with pytest.raises(ValueError):
        deliver(*bundle(), env={**ENV,key:value}, ledger=DeliveryLedger(store), clock=lambda:NOW, session=session)
    assert session.calls==0 and not store.state['entries']
