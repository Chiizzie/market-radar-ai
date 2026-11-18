import json
from unittest.mock import Mock
import pytest
import requests
from market_radar_ai.agents.comparison_live import EventClient, StorageUnavailable, event_id, envelope


def response(status=200,body=None):
    return Mock(status_code=status,content=b'{}',json=lambda:body or {'ok':True,'events':[]})


def test_commit_then_timeout_retries_without_duplicate_or_new_receipt():
    experiment='a'*64;events=[envelope('audit',{'check':'original'},'2026-11-13T15:00:00+00:00')]
    saved={};bodies=[]
    def post(*a,**kw):
        body=json.loads(kw['data']);bodies.append(kw['data']);ids=[]
        for e in body['events']:
            key=event_id(experiment,e);ids.append(key)
            saved.setdefault(key,{**e,'received_at':'2026-11-13T15:00:01+00:00'})
        if len(bodies)==1:raise requests.Timeout('ack lost after commit')
        return response(body={'ok':True,'event_ids':ids})
    EventClient('s'*32,session=Mock(post=post),sleep=Mock()).append(experiment,events)
    assert len(saved)==1 and len(bodies)==2 and bodies[0]==bodies[1]
    assert next(iter(saved.values()))['received_at']=='2026-11-13T15:00:01+00:00'


@pytest.mark.parametrize('status',[400,401,403,404])
def test_permanent_append_failures_are_not_retried(status):
    session=Mock();session.post.return_value=response(status)
    with pytest.raises(StorageUnavailable) as error:
        EventClient('s'*32,session=session,sleep=Mock()).request({'action':'append'})
    assert session.post.call_count==1 and error.value.http_status==status


def test_transient_exhaustion_is_bounded_and_diagnostics_do_not_leak():
    session=Mock();session.post.side_effect=requests.Timeout('SECRET response')
    with pytest.raises(StorageUnavailable) as error:
        EventClient('s'*32,session=session,sleep=Mock()).request({'action':'append'})
    assert session.post.call_count==3 and error.value.attempts==3
    assert error.value.diagnostic_code=='storage_timeout' and 'SECRET' not in str(error.value)


def test_wrong_append_receipt_still_fails_closed():
    session=Mock();session.post.return_value=response(body={'ok':True,'event_ids':['b'*64]})
    with pytest.raises(ValueError,match='receipt_mismatch'):
        EventClient('s'*32,session=session).append('a'*64,[envelope('audit',{},'2026-11-13T15:00:00+00:00')])
