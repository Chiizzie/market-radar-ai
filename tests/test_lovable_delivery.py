import hashlib
import hmac
import json
import pytest
from test_review_export import bundle, NOW
from market_radar_ai.dashboard.lovable_delivery import deliver, ENDPOINT

ENV = dict(GITHUB_REPOSITORY='Chiizzie/market-radar-ai',
    GITHUB_REF='refs/heads/phase-1/market-data-layer',GITHUB_EVENT_NAME='workflow_dispatch',
    GITHUB_RUN_ATTEMPT='1',SEND_LOVABLE_REVIEW='true',REVIEW_INGEST_SECRET='x'*32)

class Session:
    def __init__(self, fault=None): self.calls=0;self.fault=fault
    def post(self,url,**kw):
        self.calls+=1
        assert url==ENDPOINT and kw['allow_redirects'] is False
        body=kw['data']; headers=kw['headers']; ts=headers['X-Timestamp']
        expected=hmac.new(b'x'*32,ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
        assert headers['X-Signature']=='sha256='+expected
        data=json.loads(body)
        assert data['trade_authorized'] is False
        if self.fault=='timeout':raise TimeoutError('x'*32)
        fault=self.fault
        class Response:
            status_code=409 if fault=='duplicate' else 302 if fault=='redirect' else 200
            def json(self):return {'ok':True,'snapshot_id':'wrong' if fault=='identity' else data['snapshot_id']}
        return Response()


def test_signed_validated_export_delivered():
    session=Session()
    r=deliver(*bundle(),env=ENV,clock=lambda:NOW,session=session)
    assert r['state']=='dashboard_archive_delivery_confirmed' and session.calls==1

@pytest.mark.parametrize('fault',['timeout','duplicate','redirect','identity'])
def test_unconfirmed_delivery_redacted_and_not_retried(fault):
    session=Session(fault)
    with pytest.raises(RuntimeError) as error:
        deliver(*bundle(),env=ENV,clock=lambda:NOW,session=session)
    assert session.calls==1 and 'x'*32 not in str(error.value)

@pytest.mark.parametrize('field,value',[('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','push'),
    ('GITHUB_REPOSITORY','Chiizzie/market-radar'),('SEND_LOVABLE_REVIEW','false'),
    ('REVIEW_INGEST_SECRET','short')])
def test_disabled_scope_never_sends(field,value):
    session=Session()
    with pytest.raises(ValueError):deliver(*bundle(),env={**ENV,field:value},clock=lambda:NOW,session=session)
    assert session.calls==0


def test_invalid_audit_never_sends():
    b=bundle();b[3]['trade_authorized']=True;session=Session()
    with pytest.raises(ValueError):deliver(*b,env=ENV,clock=lambda:NOW,session=session)
    assert session.calls==0


def test_historical_artifact_tampering_rejected(tmp_path):
    from market_radar_ai.dashboard.lovable_delivery import load_pinned_bundle
    (tmp_path / 'capture.json').write_text('{}')
    with pytest.raises(ValueError, match='digest_mismatch'):
        load_pinned_bundle(tmp_path)
