import hashlib
import hmac
import json
from datetime import timedelta
import pytest
from test_dashboard_cache import capture
from test_market_capture import NOW
from market_radar_ai.dashboard.snapshot_delivery import deliver, ENDPOINT

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
        fault = self.fault
        class Response:
            status_code = 409 if fault == 'duplicate' else 302 if fault == 'redirect' else 200
            def json(self): return {'ok': True, 'snapshot_id': 'wrong' if fault == 'identity' else hashlib.sha256(kw['data']).hexdigest()}
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


@pytest.mark.parametrize('fault',['timeout','duplicate','redirect','identity'])
def test_failed_delivery_never_retries_or_leaks_secret(fault):
    session=Session(fault)
    with pytest.raises(RuntimeError) as error:
        deliver(capture(), env=ENV, clock=lambda:NOW, session=session)
    assert len(session.calls)==1 and 'x'*32 not in str(error.value)


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
