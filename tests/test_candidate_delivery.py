from copy import deepcopy
from datetime import timedelta
import hashlib
import hmac
import json
import pytest
from test_candidate_review import capture, NOW, package, answer, ENV
from market_radar_ai.agents.candidate_review import run
from market_radar_ai.dashboard.candidate_delivery import export_archive, deliver, ENDPOINT


def bundle(stale=False):
    record=package(); data=capture(); current=[NOW]
    def ask(stage,p,s):
        if stale:current[0]+=timedelta(seconds=15)
        return answer(stage,p,s)
    result=run(record,data,None,ask,clock=lambda:current[0])
    audit={'schema_version':'paid-candidate-review-v1','state':'completed','trade_authorized':False,
           'result':result,'calls':[{'stage':r['stage'],'state':'received','estimated_cost_microeur':123,
                                    'untrusted_response':r} for r in result['reviews']]}
    return record,data,None,audit


@pytest.mark.parametrize('stale',[False,True])
def test_export_rechecks_result_and_preserves_original_expiry(stale):
    args=bundle(stale); archive=export_archive(*args)
    assert hashlib.sha256(archive['package_json'].encode()).hexdigest()==archive['package_id']
    assert archive['estimated_cost_microeur']==984 and archive['review_origin']=='PAID_AI'
    assert json.loads(archive['result_json'])==args[-1]['result']
    assert archive['evidence_expires_at']==args[0]['package']['expires_at']
    assert not archive['trade_authorized'] and archive['plan'] is None


@pytest.mark.parametrize('corrupt',['citation','candidate','missing_stage','usage','verdict'])
def test_export_rejects_changed_or_incomplete_review(corrupt):
    args=bundle();audit=args[-1];r=audit['result']
    if corrupt=='citation':r['reviews'][0]['source_ids']=['fake']
    if corrupt=='candidate':r['candidate_id']='stocks:OTHER'
    if corrupt=='missing_stage':r['reviews'].pop()
    if corrupt=='usage':audit['calls'][0]['estimated_cost_microeur']=-1
    if corrupt=='verdict':r['reviews'][0]['verdict']='BUY'
    with pytest.raises((ValueError,StopIteration)):export_archive(*args)


def test_delivery_exact_signature_and_response_binding():
    class Session:
        def post(self,url,**kw):
            assert url==ENDPOINT and kw['allow_redirects'] is False
            raw=kw['data'];headers=kw['headers']
            assert headers['X-Signature']=='sha256='+hmac.new(b's'*32,headers['X-Timestamp'].encode()+b'.'+raw,hashlib.sha256).hexdigest()
            class Response:
                status_code=200
                def json(self):return {'ok':True,'archive_id':hashlib.sha256(raw).hexdigest()}
            return Response()
    r=deliver(*bundle(),env={**ENV,'SEND_CANDIDATE_REVIEW':'true','REVIEW_INGEST_SECRET':'s'*32},clock=lambda:NOW,session=Session())
    assert r['state']=='candidate_archive_delivery_confirmed'


@pytest.mark.parametrize('code',[200,302,409,500])
def test_unconfirmed_or_duplicate_delivery_never_retries(code):
    class Session:
        calls=0
        def post(self,*a,**kw):
            self.calls+=1
            class Response:
                status_code=code
                def json(self):return {'ok':True,'archive_id':'different'}
            return Response()
    s=Session()
    with pytest.raises(RuntimeError):
        deliver(*bundle(),env={**ENV,'SEND_CANDIDATE_REVIEW':'true','REVIEW_INGEST_SECRET':'s'*32},clock=lambda:NOW,session=s)
    assert s.calls==1


def test_delivery_requires_manual_authorization():
    with pytest.raises(ValueError):deliver(*bundle(),env=ENV,clock=lambda:NOW)


def test_downloaded_json_artifacts_reproduce_the_exact_archive():
    original=bundle()
    restored=json.loads(json.dumps(original))
    assert export_archive(*restored)==export_archive(*original)
