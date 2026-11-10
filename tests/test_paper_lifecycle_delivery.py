from copy import deepcopy
from unittest.mock import Mock
from test_paper_tracking import tracker,NOW
from market_radar_ai.agents.paper_outcomes import Quote
from market_radar_ai.dashboard.paper_lifecycle_delivery import notify,render

ENV={'SEND_PAPER_LIFECYCLE_TELEGRAM':'true','TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'123'}

def opened(tmp_path,monkeypatch):
    t,k,d=tracker(tmp_path,monkeypatch)
    t.observe(k,Quote(observed_at=NOW,bid=d['plan']['entry_eur'],ask=d['plan']['entry_eur']),symbol='TEST',source='synthetic',now=NOW)
    return t.report(now=NOW)

def test_persisted_entry_notification_reserves_before_send_and_caches(tmp_path,monkeypatch):
    report=opened(tmp_path,monkeypatch);ledger=Mock();session=Mock();events=[];seen=set()
    ledger.reserve.side_effect=lambda k:events.append('reserve')
    def send(*a,**kw):
        events.append('send');assert 'PAPER ENTRY RECORDED' in kw['json']['text']
        assert 'No live order' in kw['json']['text']
        return Mock(status_code=200,json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
    session.post.side_effect=send
    assert notify(report,env=ENV,now=NOW,ledger=ledger,session=session,seen=seen)['sent']==1
    assert notify(report,env=ENV,now=NOW,ledger=ledger,session=session,seen=seen)['sent']==0
    assert events==['reserve','send'];ledger.reserve.assert_called_once()

def test_uncertain_telegram_send_is_never_retried(tmp_path,monkeypatch):
    report=opened(tmp_path,monkeypatch);ledger=Mock();session=Mock();seen=set()
    session.post.side_effect=TimeoutError('sensitive')
    assert notify(report,env=ENV,now=NOW,ledger=ledger,session=session,seen=seen)['unconfirmed']==1
    notify(report,env=ENV,now=NOW,ledger=ledger,session=session,seen=seen)
    session.post.assert_called_once();ledger.confirm.assert_not_called()

def test_watch_and_unfilled_are_not_entry_notifications(tmp_path,monkeypatch):
    t,k,d=tracker(tmp_path,monkeypatch);session=Mock()
    assert notify(t.report(now=NOW),env=ENV,now=NOW,ledger=Mock(),session=session)['sent']==0
    session.post.assert_not_called()


def test_usd_entry_is_labelled_as_plan_fx_equivalent_without_altering_record(tmp_path,monkeypatch):
    report=opened(tmp_path,monkeypatch);row=report['trades'][0]
    row['outcome']['entry_fill']='9'
    original=deepcopy(row)
    text=render(row,{'symbol':'TEST','native_currency':'USD','fx_rate':'0.9'})
    assert '≈ $10.000000 USD (recorded €9.000000)' in text
    assert 'original observation FX may differ' in text
    assert 'not a fresh instruction to buy' in text
    assert row==original
    assert '$' not in render(row)
