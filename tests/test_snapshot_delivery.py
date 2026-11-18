import hashlib
import hmac
import json
from datetime import timedelta
from zoneinfo import ZoneInfo
import pytest
import requests
from test_dashboard_cache import capture
from test_market_capture import NOW
from market_radar_ai.dashboard.snapshot_delivery import SnapshotDeliveryError, deliver, ENDPOINT

ENV = dict(GITHUB_REPOSITORY='Chiizzie/market-radar-ai',
    GITHUB_REF='refs/heads/phase-1/market-data-layer', GITHUB_EVENT_NAME='workflow_dispatch',
    GITHUB_RUN_ATTEMPT='1', SEND_SCANNER_SNAPSHOT='true', REVIEW_INGEST_SECRET='x'*32)

class Session:
    def __init__(self, fault=None): self.calls=[]; self.fault=fault
    def post(self, url, **kw):
        self.calls.append(kw)
        assert url == ENDPOINT and kw['allow_redirects'] is False
        ts = kw['headers']['X-Timestamp']
        assert kw['headers']['X-Signature'] == 'sha256='+hmac.new(b'x'*32, ts.encode()+b'.'+kw['data'], hashlib.sha256).hexdigest()
        if self.fault == 'timeout': raise TimeoutError('x'*32)
        if self.fault == 'read_timeout': raise requests.ReadTimeout('sensitive detail')
        if self.fault == 'connect_timeout': raise requests.ConnectTimeout('sensitive detail')
        if self.fault == 'connection_error': raise requests.ConnectionError('sensitive detail')
        fault = self.fault
        class Response:
            status_code = 409 if fault == 'duplicate' else 302 if fault == 'redirect' else 200
            def json(self):
                if fault == 'invalid_json': raise ValueError('sensitive detail')
                if fault == 'invalid_type': return []
                return {'ok': True, 'snapshot_id': 'wrong' if fault == 'identity' else hashlib.sha256(kw['data']).hexdigest()}
        return Response()


def test_signed_capture_has_honest_status_and_no_authorization():
    session=Session()
    result=deliver(capture(), env=ENV, clock=lambda: NOW, session=session)
    body=json.loads(session.calls[0]['data'])
    assert result['trade_authorized'] is False
    assert body['markets']['crypto'][0]['decision']=='NO_ACTION'
    assert body['markets']['crypto'][0]['broker_eligibility']=='UNKNOWN'
    assert body['agents']['reports']==[]
    assert body['expires_at_epoch']==int(NOW.timestamp())+60


def test_old_capture_does_not_become_current():
    session=Session()
    deliver(capture(), env=ENV, clock=lambda: NOW+timedelta(hours=1), session=session)
    body=json.loads(session.calls[0]['data'])
    assert body['coverage']['crypto']['current']==0
    assert body['markets']['crypto'][0]['status']=='UNUSABLE_OR_STALE'


@pytest.mark.parametrize('fault,reason,code', [
    ('timeout','timeout',None), ('connect_timeout','connect_timeout',None),
    ('read_timeout','read_timeout',None), ('connection_error','connection_error',None),
    ('duplicate','http_status',409), ('redirect','http_status',302),
    ('identity','acknowledgement_mismatch',None), ('invalid_type','acknowledgement_mismatch',None),
    ('invalid_json','invalid_json',None)])
def test_failed_delivery_retains_exact_identity_without_retry_or_sensitive_data(fault, reason, code, tmp_path):
    session=Session(fault)
    archive = tmp_path/'dashboard.json'
    archive.write_text('previous render')
    with pytest.raises(SnapshotDeliveryError) as error:
        deliver(capture(), env=ENV, clock=lambda:NOW, session=session, snapshot_path=archive)
    receipt = error.value.receipt
    assert receipt['state'] == 'scanner_snapshot_delivery_unconfirmed'
    assert receipt['reason'] == reason and receipt.get('http_status') == code
    assert len(session.calls) == 1
    assert archive.read_bytes() == session.calls[0]['data']
    assert receipt['snapshot_id'] == hashlib.sha256(session.calls[0]['data']).hexdigest()
    assert receipt['coverage'] == json.loads(session.calls[0]['data'])['coverage']
    details = str(error.value) + json.dumps(receipt)
    assert 'sensitive detail' not in details and 'x'*32 not in details
    assert receipt['trade_authorized'] is False


def test_archive_failure_prevents_sending_unrecoverable_bytes(tmp_path):
    session = Session()
    with pytest.raises(OSError):
        deliver(capture(), env=ENV, clock=lambda:NOW, session=session,
                snapshot_path=tmp_path/'missing'/'dashboard.json')
    assert not session.calls


@pytest.mark.parametrize('field,value',[('GITHUB_REPOSITORY','Chiizzie/market-radar'),
    ('GITHUB_EVENT_NAME','push'),('GITHUB_RUN_ATTEMPT','2'),('SEND_SCANNER_SNAPSHOT','false'),
    ('GITHUB_REF','refs/heads/main'),('REVIEW_INGEST_SECRET','short')])
def test_scope_fails_before_network(field,value):
    session=Session()
    with pytest.raises(ValueError):
        deliver(capture(), env={**ENV,field:value}, clock=lambda:NOW, session=session)
    assert not session.calls


def test_tampered_capture_never_delivered():
    doc=capture();doc['captures'][0]['payload']['provider']='changed';session=Session()
    with pytest.raises(ValueError):deliver(doc, env=ENV, clock=lambda:NOW, session=session)
    assert not session.calls


@pytest.mark.parametrize('response_seconds,timely', [(35, True), (60, False), (80, False)])
def test_slow_acknowledgement_keeps_the_original_expiry_and_exact_receipt(response_seconds, timely):
    session = Session()
    readings = iter([NOW, NOW + timedelta(seconds=1), NOW + timedelta(seconds=response_seconds)])
    result = deliver(capture(), env=ENV, clock=lambda: next(readings), session=session)
    assert len(session.calls) == 1 and session.calls[0]['timeout'].total == 45
    assert result['expires_at_epoch'] == int(NOW.timestamp()) + 60
    assert result['acknowledged_before_expiry'] is timely
    assert result['acknowledged_at_dublin'] == (NOW + timedelta(seconds=response_seconds)).astimezone(
        ZoneInfo('Europe/Dublin')).isoformat()


def test_local_delay_bounds_the_network_budget_and_expired_requests_never_leave():
    session = Session()
    readings = iter([NOW, NOW + timedelta(seconds=54), NOW + timedelta(seconds=56)])
    receipt = deliver(capture(), env=ENV, clock=lambda: next(readings), session=session)
    assert receipt['acknowledged_before_expiry']
    assert session.calls[0]['timeout'].total == 6
    assert session.calls[0]['timeout'].connect_timeout == 6
    readings = iter([NOW, NOW + timedelta(seconds=60)])
    with pytest.raises(SnapshotDeliveryError) as expired:
        deliver(capture(), env=ENV, clock=lambda: next(readings), session=session)
    assert expired.value.receipt['reason'] == 'expired_before_send' and len(session.calls) == 1
