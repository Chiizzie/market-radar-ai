"""Delivery failures retain evidence and can never repeat an ambiguous send."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import json

import pytest
import requests

from test_paper_verdict import fixture, NOW
from test_scheduled_review import ENV
from market_radar_ai.agents.paper_verdict import finalize, export_archive, run_pipeline, STAGES
from market_radar_ai.dashboard.paper_final_delivery import deliver, PaperDeliveryError


def setup_delivery(monkeypatch, outcomes):
    _, packet, audit, _ = fixture(monkeypatch)
    archive = export_archive(packet, audit, finalize(packet, audit, {}, None, now=NOW))
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.permitted', lambda *a: True)
    env = {**ENV, 'SEND_CANDIDATE_REVIEW': 'true', 'SEND_SCHEDULED_TELEGRAM': 'true',
           'REVIEW_INGEST_SECRET': 's'*32, 'TELEGRAM_BOT_TOKEN': 'private-token',
           'TELEGRAM_CHAT_ID': '123'}
    events = []
    ledger = Mock()
    ledger.reserve.side_effect = lambda _: events.append('reserve')
    def post(url, **kw):
        if 'telegram.org' not in url:
            return Mock(status_code=200, json=lambda: {
                'ok': True, 'archive_id': hashlib.sha256(kw['data']).hexdigest()})
        events.append('send')
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception): raise outcome
        return outcome
    return archive, env, Mock(post=Mock(side_effect=post)), ledger, events


def accepted():
    return Mock(status_code=200, json=lambda: {
        'ok': True, 'result': {'chat': {'id': 123}, 'message_id': 42}})


def test_connect_timeout_retries_once_under_same_reservation(monkeypatch):
    archive, env, session, ledger, events = setup_delivery(monkeypatch, [
        requests.exceptions.ConnectTimeout('private-token'), accepted()])
    receipt = deliver(archive, env=env, clock=lambda: NOW, session=session, ledger=ledger)
    assert events == ['reserve', 'send', 'send']
    assert receipt['telegram_attempts'] == 2
    assert receipt['telegram'] == 'paper_notification_confirmed'
    ledger.confirm.assert_called_once()


@pytest.mark.parametrize('error,reason', [
    (requests.exceptions.ReadTimeout('private-token'), 'read_timeout'),
    (requests.exceptions.ConnectionError('private-token'), 'connection_error'),
    (requests.exceptions.Timeout('private-token'), 'timeout'),
    (RuntimeError('private-token'), 'transport_error')])
def test_ambiguous_post_is_never_retried_or_exposed(monkeypatch, error, reason):
    archive, env, session, ledger, events = setup_delivery(monkeypatch, [error])
    with pytest.raises(PaperDeliveryError) as caught:
        deliver(archive, env=env, clock=lambda: NOW, session=session, ledger=ledger)
    receipt = caught.value.receipt
    assert events == ['reserve', 'send']
    assert receipt['dashboard'] == 'paper_archive_delivery_confirmed'
    assert receipt['notification_ledger'] == 'reserved'
    assert receipt['failure'] == {'stage': 'telegram_send', 'reason': reason}
    assert receipt['notification_retry_allowed'] is False
    assert 'private-token' not in str(caught.value) + json.dumps(receipt)
    ledger.confirm.assert_not_called()


def test_second_connect_timeout_stops_without_confirmation(monkeypatch):
    archive, env, session, ledger, events = setup_delivery(monkeypatch, [
        requests.exceptions.ConnectTimeout(), requests.exceptions.ConnectTimeout()])
    with pytest.raises(PaperDeliveryError) as caught:
        deliver(archive, env=env, clock=lambda: NOW, session=session, ledger=ledger)
    assert events == ['reserve', 'send', 'send']
    assert caught.value.receipt['telegram'] == 'not_sent_connect_timeout'
    ledger.confirm.assert_not_called()


def test_no_retry_after_watch_expiry(monkeypatch):
    archive, env, session, ledger, events = setup_delivery(monkeypatch, [
        requests.exceptions.ConnectTimeout()])
    archive['decision']['plan']['expires_at'] = (NOW+timedelta(seconds=1)).isoformat()
    clock = lambda: NOW + (timedelta(seconds=2) if 'send' in events else timedelta())
    with pytest.raises(PaperDeliveryError) as caught:
        deliver(archive, env=env, clock=clock, session=session, ledger=ledger)
    assert events == ['reserve', 'send']
    assert caught.value.receipt['failure']['reason'] == 'expired_before_connect_retry'


@pytest.mark.parametrize('response,reason,details', [
    (Mock(status_code=429, json=lambda: {'ok': False, 'error_code': 429,
          'description': 'private-token', 'parameters': {'retry_after': 31}}),
     'provider_response_not_accepted', {'http_status': 429, 'provider_error_code': 429, 'retry_after_seconds': 31}),
    (Mock(status_code=502, json=Mock(side_effect=ValueError('private-token'))),
     'invalid_json', {'http_status': 502}),
    (Mock(status_code=200, json=lambda: {'ok': True, 'result': {'chat': {'id': 999}, 'message_id': 42}}),
     'acknowledgement_invalid', {'http_status': 200}),
    (Mock(status_code=200, json=lambda: []),
     'provider_response_not_accepted', {'http_status': 200})])
def test_bad_provider_response_keeps_bounded_evidence_without_resend(monkeypatch, response, reason, details):
    archive, env, session, ledger, events = setup_delivery(monkeypatch, [response])
    with pytest.raises(PaperDeliveryError) as caught:
        deliver(archive, env=env, clock=lambda: NOW, session=session, ledger=ledger)
    assert events == ['reserve', 'send']
    receipt = caught.value.receipt
    assert receipt['failure'] == {'stage': 'telegram_ack', 'reason': reason, **details}
    assert 'private-token' not in json.dumps(receipt)
    ledger.confirm.assert_not_called()


def test_ledger_confirmation_failure_preserves_real_ack_and_clock(monkeypatch):
    archive, env, session, ledger, events = setup_delivery(monkeypatch, [accepted()])
    ledger.confirm.side_effect = RuntimeError('private-token')
    env['RECORD_MANUAL_ALERT_CLOCK'] = 'true'
    record = Mock(return_value={'state': 'manual_ack_clock_recorded'})
    monkeypatch.setattr('market_radar_ai.agents.manual_alert_evidence.record_ack', record)
    with pytest.raises(PaperDeliveryError) as caught:
        deliver(archive, env=env, clock=lambda: NOW, session=session, ledger=ledger)
    receipt = caught.value.receipt
    assert events == ['reserve', 'send']
    assert receipt['telegram'] == 'paper_notification_confirmed'
    assert receipt['notification_ledger'] == 'confirmation_unconfirmed'
    assert receipt['acknowledged_at'] == NOW.isoformat()
    assert receipt['failure']['stage'] == 'telegram_confirm'
    record.assert_called_once()
    assert record.call_args.kwargs['acknowledged_at'] == NOW


@pytest.mark.parametrize('stage', ['render', 'reserve'])
def test_presend_failure_never_sends(monkeypatch, stage):
    archive, env, session, ledger, events = setup_delivery(monkeypatch, [])
    if stage == 'render':
        monkeypatch.setattr('market_radar_ai.dashboard.paper_final_delivery.render',
                            Mock(side_effect=ValueError('private-token')))
    else:
        ledger.reserve.side_effect = ValueError('delivery_already_attempted_do_not_retry')
    with pytest.raises(PaperDeliveryError) as caught:
        deliver(archive, env=env, clock=lambda: NOW, session=session, ledger=ledger)
    assert 'send' not in events
    assert caught.value.receipt['failure']['stage'] == 'telegram_'+stage


def test_archive_timeout_prevents_telegram_and_has_no_retry(monkeypatch):
    archive, env, session, ledger, _ = setup_delivery(monkeypatch, [])
    session.post.side_effect = requests.exceptions.ReadTimeout('private-token')
    with pytest.raises(PaperDeliveryError) as caught:
        deliver(archive, env=env, clock=lambda: NOW, session=session, ledger=ledger)
    session.post.assert_called_once()
    ledger.reserve.assert_not_called()
    assert caught.value.receipt['failure'] == {'stage': 'dashboard_send', 'reason': 'read_timeout'}


def test_pipeline_saves_completed_decision_and_receipt_without_paid_repeat(monkeypatch, tmp_path):
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from market_radar_ai.agents.github_budget import GitHubSpendingLedger
    from test_github_budget import MemoryStore
    fixture(monkeypatch)
    client = OpenAIPilot(api_key='fake', ledger=GitHubSpendingLedger(MemoryStore()),
                        eur_per_usd='0.9', enabled=True)
    calls = []
    def call(**kw):
        calls.append(json.loads(kw['prompt'])['stage'])
        return SimpleNamespace(data={'verdict': 'APPROVE_PAPER', 'rationale': 'Synthetic',
                                     'source_ids': ['news:test'], 'concerns': []})
    monkeypatch.setattr(client, 'call', call)
    failure = PaperDeliveryError({'dashboard': 'paper_archive_delivery_confirmed',
        'telegram': 'not_confirmed', 'trade_authorized': False}, 'telegram_send', 'read_timeout')
    delivery = Mock(side_effect=failure)
    with pytest.raises(PaperDeliveryError):
        run_pipeline({}, None, client=client, root=tmp_path/'first', refresh=lambda _: ({}, None),
                     deliver=delivery, clock=lambda: NOW, enabled=True)
    status = json.loads((tmp_path/'first/status.json').read_text())
    receipt = json.loads((tmp_path/'first/delivery.json').read_text())
    assert status['state'] == 'paper_decision_delivery_failed'
    assert status['model_calls'] == 8 and status['automatic_paid_retry'] is False
    assert receipt == failure.receipt
    assert json.loads((tmp_path/'first/decision.json').read_text())['verdict'] == 'PAPER_WATCH_FOR_ENTRY'
    second = run_pipeline({}, None, client=client, root=tmp_path/'second',
        refresh=lambda _: ({}, None), deliver=delivery, clock=lambda: NOW, enabled=True)
    assert second['state'] == 'paper_setup_already_attempted'
    assert calls == STAGES
    delivery.assert_called_once()


def test_readonly_probe_uses_only_get_methods_and_redacts_bodies(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    from verify_telegram_readonly import probe
    session = Mock()
    session.get.side_effect = [
        Mock(status_code=200, json=lambda: {'ok': True, 'result': {'is_bot': True, 'username': 'private-token'}}),
        Mock(status_code=403, json=lambda: {'ok': False, 'error_code': 403, 'description': 'private-token'})]
    report = probe({'TELEGRAM_BOT_TOKEN': 'private-token', 'TELEGRAM_CHAT_ID': '123'}, session)
    assert [r['state'] for r in report['checks']] == ['confirmed', 'not_confirmed']
    assert [c.args[0].rsplit('/', 1)[-1] for c in session.get.call_args_list] == ['getMe', 'getChat']
    assert 'private-token' not in json.dumps(report)
    assert report['notifications_sent'] == report['model_calls'] == 0
    session.post.assert_not_called()
