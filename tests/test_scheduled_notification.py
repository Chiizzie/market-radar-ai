from unittest.mock import Mock
import pytest
from test_candidate_delivery import bundle
from test_scheduled_review import ENV, NOW
from market_radar_ai.dashboard.scheduled_notification import deliver

ENV = {**ENV,'SEND_SCHEDULED_TELEGRAM':'true','TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'123'}

def test_notification_is_no_action_and_reserved_before_send():
    events=[]; ledger=Mock();ledger.reserve.side_effect=lambda _:events.append('reserve')
    session=Mock()
    def post(*a,**kw):
        events.append('post');assert kw['json']['text'].startswith('ℹ️ NO ACTION')
        assert 'No approved trade' in kw['json']['text']
        return Mock(status_code=200,json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
    session.post.side_effect=post
    assert deliver(*bundle(),env=ENV,clock=lambda:NOW,ledger=ledger,session=session)['state']=='telegram_research_delivery_confirmed'
    assert events==['reserve','post'];ledger.confirm.assert_called_once()

def test_uncertain_delivery_never_retries():
    session=Mock();session.post.side_effect=TimeoutError('secret must not leak');ledger=Mock()
    with pytest.raises(RuntimeError,match='do not retry'):deliver(*bundle(),env=ENV,clock=lambda:NOW,ledger=ledger,session=session)
    session.post.assert_called_once();ledger.confirm.assert_not_called()

def test_duplicate_reservation_prevents_post():
    session=Mock();ledger=Mock();ledger.reserve.side_effect=ValueError('duplicate')
    with pytest.raises(ValueError):deliver(*bundle(),env=ENV,clock=lambda:NOW,ledger=ledger,session=session)
    session.post.assert_not_called()

def test_disabled_sends_nothing():
    assert deliver(None,None,None,None,env={},clock=lambda:NOW)=={'state':'disabled'}
