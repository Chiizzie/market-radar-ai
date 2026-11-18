from copy import deepcopy
from datetime import timedelta
import json
from unittest.mock import Mock

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.comparison_checkpoint import save
from market_radar_ai.agents.comparison_live import LiveComparison, StorageUnavailable
from market_radar_ai.agents.comparison_watcher import run
from market_radar_ai.agents.outage_exit_evidence import record, verified
from market_radar_ai.agents.paper_comparison import aware
from test_comparison_live import environment
from test_scheduled_collection import ENV


@pytest.mark.parametrize('ahead,duration,standby,batches', [(39,46,0,7),(559,330,270,3)])
def test_startup_outage_retains_guarded_deadline_references_without_appending(tmp_path, monkeypatch, ahead, duration, standby, batches):
    worker, packet, _, t, _, client = environment(tmp_path, monkeypatch)
    worker.enrol(packet, now=t[0])
    t[0] += timedelta(seconds=1)
    worker.poll()
    deadline = aware(packet['packet']['plan']['exit_by'])
    assert worker.store.report(now=deadline-timedelta(seconds=31))['rows'][0]['code_only']['state']=='open_simulation'
    secret = 's'*36
    save(worker, tmp_path/'prefix', secret)
    seen = len(client.events)
    journal = (worker.root/'comparison-events.jsonl').read_bytes()
    source = Mock()
    source.read.side_effect = StorageUnavailable('storage_timeout', 3)
    clock_start = deadline - timedelta(seconds=ahead)
    seconds = [0.]
    def clock():
        return clock_start + timedelta(seconds=seconds[0])
    def sleep(n):
        seconds[0] += n
    def fetch(decisions):
        assert len(decisions) == 1 and deadline - timedelta(seconds=30) <= clock() <= deadline
        d, = decisions
        q = {'observed_at': clock().isoformat(), 'bid':'99', 'ask':'99.01'}
        return [{'packet_id':d['packet_id'], 'symbol':d['plan']['symbol'], 'quote':q,'source':'alpaca_iex:'+'a'*64}], []
    target = tmp_path/'observed'
    observer = Mock()
    observer.fetch.side_effect = fetch
    cold = LiveComparison(target, client=source, observer=observer, clock=clock)
    report = run(env={**ENV, 'RESEARCH_CHECKPOINT_DIR':str(tmp_path/'prefix'), 'REVIEW_INGEST_SECRET':secret},
        output=target, duration=duration, interval=5, exit_standby_seconds=standby, clock=clock,
        monotonic=lambda:seconds[0], sleep=sleep, factory=lambda:cold)
    assert report['critical_failure'] and report['startup_state']=='failed' and report['polls']==report['quotes_received']==0
    assert report['outage_exit_evidence']=={'polls':batches,'references':batches,'failure_count':0}
    source.append.assert_not_called()
    assert len(client.events)==seen and (target/'comparison-events.jsonl').read_bytes()==journal
    document=json.loads((target/'outage-exit-evidence.json').read_text())
    result=verified(document)
    if standby:
        assert result['sampling']=='preceding_dispatch'
        assert [(deadline-aware(row['received_at'])).total_seconds() for row in result['quotes']]==[28,18,8]
    assert result['source_cursor']==worker.cursor and result['applied_to_ledger'] is False
    assert all(x['spread_quality']=='within_guard' and x['packet_id']==packet['packet_id'] for x in result['quotes'])
    for key, value in [('received_at',(deadline+timedelta(seconds=1)).isoformat()),('source','other'),('spread_quality','wide')]:
        changed=deepcopy(result)
        changed['quotes'][0][key]=value
        with pytest.raises(ValueError,match='invalid_outage_exit_reference'):
            verified({'report':changed,'sha256':digest(changed)})
    with pytest.raises(ValueError,match='invalid_outage_exit_evidence'):
        verified({**document,'sha256':'0'*64})


def test_missing_checkpoint_outside_deadline_and_closed_scope_make_no_provider_requests(tmp_path, monkeypatch):
    worker, packet, _, t, _, _=environment(tmp_path,monkeypatch)
    worker.enrol(packet,now=t[0]);t[0]+=timedelta(seconds=1);worker.poll()
    worker.observer=Mock()
    args=dict(clock=lambda:t[0],monotonic=lambda:0,sleep=Mock(),end=5,interval=5,in_scope=lambda at:True)
    assert record(worker,**args) is None
    worker.health['checkpoint_state']='restored'
    assert record(worker,**args) is None
    t[0] = aware(packet['packet']['plan']['exit_by']) - timedelta(seconds=3)
    assert record(worker,**{**args,'in_scope':lambda at:False}) is None
    t[0]+=timedelta(seconds=5)
    assert record(worker,**args) is None
    worker.observer.fetch.assert_not_called()


def test_repeated_wide_quotes_are_retained_once_and_late_receipts_are_excluded(tmp_path, monkeypatch):
    worker, packet, _, t, _, _=environment(tmp_path,monkeypatch)
    worker.enrol(packet,now=t[0]);t[0]+=timedelta(seconds=1);worker.poll()
    worker.health['checkpoint_state']='restored'
    deadline=aware(packet['packet']['plan']['exit_by'])
    now=[deadline-timedelta(seconds=10)]
    def elapsed():
        return (now[0]-deadline).total_seconds()+10
    def sleep(s):
        now[0]+=timedelta(seconds=s)
    def fetch(decisions):
        d,=decisions
        at=deadline-timedelta(seconds=10)
        if now[0]==deadline:
            at=now[0]
            sleep(1)
        return [{'packet_id':d['packet_id'],'symbol':d['plan']['symbol'],'source':'alpaca_iex:'+'1'*64,
                 'quote':{'observed_at':at.isoformat(),'bid':'95','ask':'105'}}],[]
    worker.observer=Mock()
    worker.observer.fetch.side_effect=fetch
    stats=record(worker,clock=lambda:now[0],monotonic=elapsed,sleep=sleep,end=13,interval=5,in_scope=lambda at:True)
    assert stats=={'polls':3,'references':1,'failure_count':0}
    report=verified(json.loads((worker.root/'outage-exit-evidence.json').read_text()))
    assert report['quotes'][0]['spread_quality']=='wide'
    assert report['quotes'][0]['received_at']==(deadline-timedelta(seconds=10)).isoformat()
