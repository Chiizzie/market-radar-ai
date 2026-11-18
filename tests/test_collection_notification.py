from unittest.mock import Mock
import pytest
from test_scheduled_collection import ENV,NOW
from market_radar_ai.dashboard.collection_notification import notify

ENV={**ENV,'SEND_COLLECTION_TELEGRAM':'true','TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'123'}


def test_late_receipt_reports_archival_delivery_and_skips_opening_alert():
    receipt = {'state': 'scanner_snapshot_delivery_confirmed', 'acknowledged_before_expiry': False}
    session, ledger = Mock(), Mock()
    session.post.return_value = Mock(status_code=200, json=lambda: {
        'ok': True, 'result': {'chat': {'id': 123}, 'message_id': 1}})
    notify({'delivery': receipt, 'opening_session': {'window': 'premarket'}},
           env=ENV, clock=lambda: NOW, session=session, ledger=ledger)
    message = session.post.call_args.kwargs['json']['text']
    assert 'acknowledgement arrived after expiry' in message and 'Paper review skipped' in message
    assert 'OPENING UPDATE' not in message

def test_delivery_status_is_independent_of_paid_review_and_reserved_before_send():
    events=[];ledger=Mock();ledger.reserve.side_effect=lambda _:events.append('reserve')
    session=Mock()
    def post(*a,**kw):
        events.append('post');assert 'Paid AI is paused' in kw['json']['text']
        assert kw['json']['text'].startswith('ℹ️ NO ACTION')
        return Mock(status_code=200,json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
    session.post.side_effect=post
    r=notify({'delivery':{'state':'scanner_snapshot_delivery_confirmed','coverage':{}}},env=ENV,clock=lambda:NOW,session=session,ledger=ledger)
    assert r['model_calls']==0 and events==['reserve','post']
    ledger.confirm.assert_called_once()


def test_duplicate_hour_never_sends():
    ledger=Mock();ledger.reserve.side_effect=ValueError('delivery_already_attempted_do_not_retry');session=Mock()
    assert notify({},env=ENV,clock=lambda:NOW,session=session,ledger=ledger)['state']=='collection_notice_already_attempted'
    session.post.assert_not_called()


def test_failure_is_not_a_success_and_unknown_delivery_never_retries():
    ledger=Mock();session=Mock();session.post.side_effect=TimeoutError()
    with pytest.raises(RuntimeError):notify({},env=ENV,clock=lambda:NOW,session=session,ledger=ledger)
    assert session.post.call_args.kwargs['json']['text'].startswith('⚠️ SCANNER FAILURE')
    session.post.assert_called_once();ledger.confirm.assert_not_called()


@pytest.mark.parametrize('reason,status,text', [('read_timeout',None,'timed out'), ('http_status',503,'HTTP 503'),
                                               ('invalid_json',None,'could not be verified')])
def test_storage_failure_identifies_collection_and_skipped_review(reason, status, text):
    ledger=Mock()
    session=Mock()
    session.post.return_value=Mock(status_code=200,json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
    result=notify({'delivery':{'state':'scanner_snapshot_delivery_unconfirmed','reason':reason,'http_status':status,
        'coverage':{'stocks':{'current':80,'attempted':80,'unusable_or_stale':0}}}},
        env=ENV,clock=lambda:NOW,session=session,ledger=ledger)
    message=session.post.call_args.kwargs['json']['text']
    assert result['category']=='failed' and text in message
    assert 'Market data collected.' in message and 'Paper review skipped' in message and '80/80 current' in message
    ledger.reserve.assert_called_once()
    ledger.confirm.assert_called_once()
