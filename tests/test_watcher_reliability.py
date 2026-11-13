import json
from unittest.mock import Mock
import pytest
import requests
from market_radar_ai.agents.comparison_live import EventClient, StorageUnavailable
from market_radar_ai.agents.comparison_watcher import run
from market_radar_ai.agents.watcher_diagnostics import record_failure
from test_paper_watcher import Clock, ENV


def response(status=200, body=None):
    return Mock(status_code=status,content=b'{}',json=lambda: body or {'ok':True,'events':[]})


def test_read_retries_transient_and_resigns_each_attempt():
    c=Clock(); session=Mock(); session.post.side_effect=[requests.Timeout('secret body'),response(503),response()]
    client=EventClient('s'*32,session=session,clock=c.now,sleep=c.sleep)
    assert client.request({'action':'read'})['ok']
    assert session.post.call_count==3 and c.elapsed==1.5
    assert session.post.call_args_list[0].kwargs['headers']['X-Timestamp']!=session.post.call_args_list[-1].kwargs['headers']['X-Timestamp']


@pytest.mark.parametrize('status',[400,401,403,404])
def test_auth_and_validation_not_retried(status):
    session=Mock();session.post.return_value=response(status)
    with pytest.raises(StorageUnavailable) as error:
        EventClient('s'*32,session=session,sleep=Mock()).request({'action':'read'})
    assert session.post.call_count==1 and error.value.http_status==status


def test_unknown_write_ack_retries_exact_envelope_and_sanitizes_diagnostics():
    session=Mock();session.post.side_effect=requests.Timeout('private-token-and-provider-body')
    with pytest.raises(StorageUnavailable) as error:
        EventClient('s'*32,session=session,sleep=Mock()).request({'action':'append'})
    assert session.post.call_count==3
    assert len({call.kwargs['data'] for call in session.post.call_args_list}) == 1
    health={};record_failure(health,error.value,Clock().now())
    assert health['last_failure']=={'code':'storage_timeout','attempts':3}
    assert 'private-token' not in json.dumps(health)+str(error.value)


def test_read_retry_exhaustion_bounded():
    session=Mock();session.post.return_value=response(429);sleep=Mock()
    with pytest.raises(StorageUnavailable) as error:
        EventClient('s'*32,session=session,sleep=sleep).request({'action':'read'})
    assert session.post.call_count==3 and sleep.call_count==2 and error.value.attempts==3


def test_slow_replay_exposed_and_does_not_make_up_quotes(tmp_path):
    c=Clock();comparison=Mock();comparison.health={'polls':0,'quotes_received':0,'error_polls':0}
    def fail():
        c.sleep(20)
        raise StorageUnavailable('storage_timeout',3)
    comparison.poll.side_effect=fail
    result=run(env=ENV,output=tmp_path,duration=10,clock=c.now,monotonic=lambda:c.elapsed,sleep=c.sleep,factory=lambda:comparison)
    assert result['state']=='completed_with_gaps' and result['quotes_received']==0
    assert result['maximum_poll_duration_seconds']==20
    assert result['comparison']['failure_counts']=={'storage_timeout':1}
    comparison.close.assert_called_once()


def test_workflow_isolates_comparison_credentials_and_keeps_backup():
    from pathlib import Path
    s=Path('.github/workflows/scheduled-scanner.yml').read_text()
    paper=s.split('  paper-watcher:')[1].split('  comparison-watcher:')[0]
    comparison=s.split('  comparison-watcher:')[1].split('  method-shadow:')[0]
    assert 'comparison_watcher --duration' not in paper and 'REVIEW_INGEST_SECRET' not in paper
    assert 'comparison_watcher --duration' in comparison and 'comparison-recovery-' in comparison
    assert 'TELEGRAM_BOT_TOKEN' not in comparison and 'OPENAI_API_KEY' not in comparison
