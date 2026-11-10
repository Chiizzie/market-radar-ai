from datetime import datetime,timedelta
from unittest.mock import Mock
import hashlib,json
from test_paper_verdict import fixture,NOW
from market_radar_ai.agents.paper_verdict import finalize,export_archive
from market_radar_ai.dashboard.paper_final_delivery import deliver,render
from test_scheduled_review import ENV


def test_signed_dashboard_and_durable_telegram_delivery(monkeypatch):
    _,packet,audit,_=fixture(monkeypatch)
    archive=export_archive(packet,audit,finalize(packet,audit,{},None,now=NOW))
    # Use the real dispatcher scope predicate with this deterministic weekday.
    import market_radar_ai.agents.scheduled_review as scheduled
    monkeypatch.setattr(scheduled,'permitted',lambda *a:True)
    session=Mock();ledger=Mock();events=[]
    ledger.reserve.side_effect=lambda _:events.append('reserve')
    def post(url,**kw):
        if 'telegram.org' in url:
            events.append('telegram');assert kw['json']['text'].startswith('🧪 WAIT FOR BREAKOUT')
            assert 'Not a live trade instruction' in kw['json']['text']
            return Mock(status_code=200,json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
        events.append('dashboard')
        assert kw['headers']['X-Signature'].startswith('sha256=')
        return Mock(status_code=200,json=lambda:{'ok':True,'archive_id':hashlib.sha256(kw['data']).hexdigest()})
    session.post.side_effect=post
    env={**ENV,'SEND_CANDIDATE_REVIEW':'true','SEND_SCHEDULED_TELEGRAM':'true',
         'REVIEW_INGEST_SECRET':'s'*32,'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'123'}
    r=deliver(archive,env=env,clock=lambda:NOW,session=session,ledger=ledger)
    assert events==['dashboard','reserve','telegram']
    assert r['telegram']=='paper_notification_confirmed';ledger.confirm.assert_called_once()
    assert render(archive,NOW+timedelta(minutes=5)).startswith('ℹ️ NO PAPER ENTRY')


def test_stock_alert_requires_breakout_and_uses_plan_fx_without_rewriting_archive(monkeypatch):
    from copy import deepcopy
    _,packet,audit,_=fixture(monkeypatch)
    archive=export_archive(packet,audit,finalize(packet,audit,{},None,now=NOW))
    p=archive['decision']['plan']
    p.update(native_currency='USD',fx_rate='0.9',entry_eur='5.0495445',stop_eur='4.986',target_eur='5.237228034')
    original=deepcopy(archive)
    text=render(archive,NOW)
    assert 'WATCH ONLY' in text and 'do not enter just because' in text
    assert 'BREAKOUT TRIGGER: reference ask reaches $5.610605 USD or above.' in text
    assert 'Stop $5.54 USD | target $5.819142 USD' in text
    assert 'No qualifying trigger by then = SKIP' in text and 'Dublin' in text
    assert '€20 limit' in text and 'manual purchases appear under Account' in text
    assert archive==original
    assert '$5.610605' not in render(archive,datetime.fromisoformat(p['expires_at']))


def test_native_eur_watch_is_never_relabelled_usd(monkeypatch):
    _,packet,audit,_=fixture(monkeypatch)
    archive=export_archive(packet,audit,finalize(packet,audit,{},None,now=NOW))
    archive['decision']['plan']['native_currency']='EUR'
    text=render(archive,NOW)
    assert 'BREAKOUT TRIGGER' in text and 'EUR or above' in text and '$' not in text
