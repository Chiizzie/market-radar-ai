import json
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from test_paper_verdict import NOW, fixture
from market_radar_ai.agents.comparison_live import LiveComparison, event_id, restore_events
from market_radar_ai.agents.paper_verdict import finalize


class MemoryEvents:
    def __init__(self): self.events = []; self.fail = False
    def append(self, experiment, events):
        if self.fail: raise RuntimeError('comparison_storage_unavailable')
        for e in events:
            eid = event_id(experiment, e)
            if any(x['event_id'] == eid for x in self.events): continue
            self.events.append({**e, 'event_id': eid, 'experiment_id': experiment,
                'day': e['occurred_at'][:10], 'seq': len(self.events)+1})
    def read(self, experiment, day, after):
        if self.fail: raise RuntimeError('comparison_storage_unavailable')
        page = [e for e in self.events if e['experiment_id']==experiment and e['day']==day and e['seq']>after][:3]
        return {'events': page, 'next': page[-1]['seq'] if page else after}


def environment(tmp_path, monkeypatch):
    _, packet, audit, _ = fixture(monkeypatch)
    time = [NOW]
    client = MemoryEvents()
    price = [packet['packet']['plan']['entry_eur']]
    observer = SimpleNamespace(fetch=lambda decisions: ([{
        'packet_id': d['packet_id'], 'quote': {'observed_at': time[0].isoformat(), 'bid': price[0], 'ask': price[0]},
        'source': 'alpaca_iex:'+'a'*64} for d in decisions], []))
    store = LiveComparison(tmp_path/'one', client=client, observer=observer, clock=lambda:time[0])
    return store, packet, audit, time, price, client


def test_durable_baseline_before_review_rejection_and_restore(tmp_path, monkeypatch):
    s,p,a,t,price,client = environment(tmp_path,monkeypatch)
    s.enrol(p, now=t[0]); t[0]+=timedelta(seconds=1); s.poll()
    t[0]+=timedelta(seconds=1); s.begin_review(p, now=t[0])
    a['reviews'][3]['verdict']='REJECT'; a['completed_at']=t[0].isoformat()
    decision=finalize(p,a,{},None,now=t[0])
    s.record_review(p,a,decision,now=t[0])
    price[0]=p['packet']['plan']['target_eur'];t[0]+=timedelta(seconds=1);s.poll()
    report=s.close()
    assert report['code_only']['closed']==1
    assert report['ai_reviewed']['states']=={'no_action':1}
    assert report['rows'][0]['rejected_counterfactual_only']
    assert [e['kind'] for e in client.events][:3]==['enrol','quote','begin']
    restored=restore_events(s.root/'comparison-events.jsonl',tmp_path/'restored',client=client,day=s.day)
    assert restored.report(now=t[0])==s.store.report(now=t[0])
    second=LiveComparison(tmp_path/'two',client=client,clock=lambda:t[0]);second.sync()
    assert second.store.report(now=t[0])==s.store.report(now=t[0])
    second.sync();assert len(second.seen)==len([e for e in client.events if e['experiment_id']==s.experiment])
    assert all(e['experiment_id']!=s.experiment for e in client.events if e['kind']=='setup_report')


def test_idle_poll_reads_once_and_active_poll_validates_its_durable_quote(tmp_path,monkeypatch):
    worker,packet,_,clock,_,client=environment(tmp_path,monkeypatch)
    read=client.read; reads=[]
    def counted(experiment,day,after):
        reads.append(after)
        return read(experiment,day,after)
    client.read=counted
    worker.poll()
    assert reads==[0] and worker.health['quotes_received']==0
    worker.enrol(packet,now=clock[0])
    reads.clear();clock[0]+=timedelta(seconds=1)
    worker.poll()
    assert len(reads)==2 and worker.health['last_sync']['pages']==1
    assert client.events[-1]['event_id'] in worker.seen
    client.append=lambda experiment,rows: None
    clock[0]+=timedelta(seconds=1)
    with pytest.raises(ValueError,match='acknowledged_event_missing'):
        worker.poll()
    assert worker.health['quotes_received']==1


def test_receipt_bound_read_leaves_concurrent_later_pages_for_full_sync(tmp_path,monkeypatch):
    first,packet,_,clock,_,client=environment(tmp_path,monkeypatch)
    first.enrol(packet,now=clock[0])
    for _ in range(2):
        clock[0]+=timedelta(seconds=1);first.poll()
    events=client.events.copy()
    def pages(experiment,day,after):
        page=[e for e in events if e['seq']>after][:1]
        return {'events':page,'next':page[-1]['seq'] if page else after}
    client.read=pages
    second=LiveComparison(tmp_path/'separate',client=client,clock=lambda:clock[0])
    second.sync(through_event_ids={events[1]['event_id']})
    assert second.cursor==events[1]['seq'] and events[2]['event_id'] not in second.seen
    second.sync()
    assert second.seen==first.seen and second.store.report(now=clock[0])==first.store.report(now=clock[0])


def test_unreviewed_cohort_survives_writer_restart(tmp_path,monkeypatch):
    s,p,_,t,price,client=environment(tmp_path,monkeypatch)
    s.enrol(p,now=t[0]);t[0]+=timedelta(seconds=2)
    restarted=LiveComparison(tmp_path/'restarted',client=client,clock=lambda:t[0],observer=s.observer)
    restarted.poll()
    assert restarted.store.report(now=t[0])['code_only']['states']=={'open_simulation':1}
    assert restarted.store.report(now=t[0])['ai_reviewed']['states']=={'not_reviewed':1}


def test_failed_storage_never_counts_a_quote_or_starts_review(tmp_path,monkeypatch):
    s,p,_,t,_,client=environment(tmp_path,monkeypatch)
    s.enrol(p,now=t[0]);client.fail=True
    with pytest.raises(RuntimeError):s.start_observing()
    assert s.thread is None
    assert s.health['quotes_received']==0
    assert [e['kind'] for e in client.events]==['enrol']


def test_hash_tampering_and_invalid_review_refused_before_write(tmp_path,monkeypatch):
    s,p,a,t,_,client=environment(tmp_path,monkeypatch)
    s.enrol(p,now=t[0]);s.begin_review(p,now=t[0])
    d=finalize(p,a,{},None,now=t[0]);d['trade_authorized']=True
    with pytest.raises(ValueError):s.record_review(p,a,d,now=t[0])
    assert len(client.events)==2
    corrupted=deepcopy(client.events[0]);corrupted['payload_json']='{}'
    other=LiveComparison(tmp_path/'other',client=client,clock=lambda:t[0])
    with pytest.raises(ValueError,match='invalid_comparison_event'):other.apply(corrupted)


def test_idempotent_enrolment_preserves_original_clock(tmp_path,monkeypatch):
    s,p,_,t,_,client=environment(tmp_path,monkeypatch)
    s.enrol(p,now=t[0]);t[0]+=timedelta(seconds=1);s.enrol(p,now=t[0])
    assert len(client.events)==1
    assert s.store.report(now=t[0])['rows'][0]['enrolled_at']==NOW.isoformat()


def test_batch_enrolment_deduplicates_and_starts_before_any_model(tmp_path,monkeypatch):
    from market_radar_ai.agents.github_budget import GitHubSpendingLedger
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from market_radar_ai.agents.paper_verdict import run_pipeline
    from test_github_budget import MemoryStore
    s,p,_,t,_,events=environment(tmp_path,monkeypatch)
    s.enrol_many([p,p],now=t[0]);assert len(events.events)==1
    client=OpenAIPilot(api_key='fake',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='0.9',enabled=True)
    calls=[];monkeypatch.setattr(client,'call',lambda **kw:calls.append(kw))
    events.fail=True
    with pytest.raises(RuntimeError):
        run_pipeline({},None,client=client,root=tmp_path/'pipeline',refresh=lambda x:({},None),
                     deliver=lambda x:None,clock=lambda:t[0],enabled=True,comparison=s)
    assert calls==[]
