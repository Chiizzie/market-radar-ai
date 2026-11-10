from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from market_radar_ai.agents import execution_research as execution
from market_radar_ai.agents.candidate_packages import digest


def test_current_execution_is_a_separate_fixed_experiment():
    execution.validate_source_protocol()
    assert execution.SOURCE_PROTOCOL_ID == 'abfaa5c8b4fd3e76a46dddd142bd4747765b32c0caf2c6122afe9dbff6c7e4e8'
    assert execution.EXPERIMENT == '530424b310fd4096a2871f1b0ac814cab436a2f47879231c17cff1ed3a251d36'
    assert execution.PROTOCOL['source_protocol_id'] == digest(execution.SOURCE_PROTOCOL)


def test_changed_strategy_cannot_silently_reuse_execution_series(monkeypatch,tmp_path):
    monkeypatch.setattr(execution,'SOURCE_PROTOCOL',{**execution.SOURCE_PROTOCOL,'review_policy_version':'future'})
    with pytest.raises(ValueError,match='execution_source_protocol_mismatch'):
        execution.collect(None,now=datetime(2026,11,10,tzinfo=timezone.utc),root=tmp_path)


def test_collector_requests_only_current_protocol_across_days(tmp_path):
    calls=[]
    class Client:
        def read(self,experiment,day,after):
            calls.append((experiment,day,after));return {'events':[],'next':after}
    assert execution.collect(Client(),now=datetime(2026,11,10,tzinfo=timezone.utc),root=tmp_path)==[]
    assert calls==[(execution.SOURCE_PROTOCOL_ID,f'2026-11-{n:02d}',0) for n in (8,9,10)]


def test_report_keeps_original_source_time_separate_from_generation():
    from test_execution_research import event,body,NOW
    b=body();packet={'packet':b,'packet_id':digest(b)}
    events=[event(1,'enrol',{'packet':packet})]
    report=execution.replay(events,now=NOW.replace(day=10))
    assert report['as_of']!=report['source_last_at']
    assert report['source_last_at']==events[0]['occurred_at']
    assert report['source_protocol_id']==execution.SOURCE_PROTOCOL_ID
