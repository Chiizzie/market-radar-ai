import gzip
import json
from datetime import timedelta
from unittest.mock import Mock
import pytest
import requests
from test_comparison_live import environment
from test_watcher_reliability import response
from market_radar_ai.agents.comparison_live import EventClient, LiveComparison, event_id, envelope
from market_radar_ai.agents.comparison_checkpoint import restore, save, signature, file_hash

SECRET = 'test-only-'*4


def test_cached_prefix_and_server_tail_match_cold_replay(tmp_path,monkeypatch):
    first,p,_,t,_,client=environment(tmp_path,monkeypatch)
    first.enrol(p,now=t[0]);t[0]+=timedelta(seconds=1);first.poll()
    cache=tmp_path/'cache';assert save(first,cache,SECRET)
    prefix=first.cursor
    t[0]+=timedelta(seconds=1);first.poll()
    warm=LiveComparison(tmp_path/'warm',client=client,clock=lambda:t[0])
    assert restore(warm,cache,SECRET) and warm.cursor==prefix
    read=client.read;client.read=Mock(side_effect=read)
    warm.sync()
    assert client.read.call_args_list[0].args[2]==prefix
    cold=LiveComparison(tmp_path/'cold',client=client,clock=lambda:t[0]);cold.sync()
    assert warm.store.report(now=t[0])==cold.store.report(now=t[0])
    assert (warm.root/'comparison-events.jsonl').read_bytes()==(cold.root/'comparison-events.jsonl').read_bytes()
    assert warm.health['checkpoint_state']=='restored'


@pytest.mark.parametrize('fault',['hmac','data','day','protocol','cursor','secret','missing','semantic','order'])
def test_bad_checkpoint_falls_back_without_partial_state(tmp_path,monkeypatch,fault):
    first,p,_,t,_,client=environment(tmp_path,monkeypatch)
    first.enrol(p,now=t[0]);t[0]+=timedelta(seconds=1);first.poll()
    cache=tmp_path/'cache';save(first,cache,SECRET)
    path=cache/'manifest.json';sealed=json.loads(path.read_text());m=sealed['manifest']
    if fault=='hmac':sealed['hmac']='0'*64
    if fault=='data':(cache/'events.jsonl.gz').write_bytes(b'tampered')
    if fault=='day':m['day']='2026-01-01'
    if fault=='protocol':m['experiment']='a'*64
    if fault=='cursor':m['cursor']+=1
    if fault=='missing':(cache/'events.jsonl.gz').unlink()
    if fault in ('semantic','order'):
        events=[json.loads(line) for line in gzip.decompress((cache/'events.jsonl.gz').read_bytes()).splitlines()]
        if fault=='semantic':
            payload=json.loads(events[-1]['payload_json']);payload['candidate_id']='stocks:NOTENROLLED'
            events[-1]['payload_json']=json.dumps(payload)
            events[-1]['event_id']=event_id(first.experiment,events[-1])
        else:events[-1]['seq']=events[0]['seq']
        raw=b''.join((json.dumps(e)+'\n').encode() for e in events)
        (cache/'events.jsonl.gz').write_bytes(gzip.compress(raw));m['bytes']=len(raw)
        m['sha256']=file_hash(cache/'events.jsonl.gz')
    if fault!='hmac':sealed['hmac']=signature(SECRET,m)
    path.write_text(json.dumps(sealed))
    warm=LiveComparison(tmp_path/'warm',client=client,clock=lambda:t[0])
    assert not restore(warm,cache,'wrong-secret'*4 if fault=='secret' else SECRET)
    assert warm.cursor==0 and not warm.seen and not (warm.root/'comparison-events.jsonl').exists()
    warm.sync()
    assert warm.store.report(now=t[0])==first.store.report(now=t[0])


def test_lost_append_ack_reuses_original_event_and_database_receipt():
    experiment='a'*64;events=[envelope('audit',{'value':'original'},'2026-11-13T15:00:00+00:00')]
    saved={};bodies=[]
    def post(*a,**kw):
        body=json.loads(kw['data']);bodies.append(kw['data'])
        ids=[]
        for e in body['events']:
            key=event_id(experiment,e);ids.append(key)
            saved.setdefault(key,{**e,'received_at':'2026-11-13T15:00:01+00:00'})
        if len(bodies)==1:raise requests.Timeout('ack lost after commit')
        return response(body={'ok':True,'event_ids':ids})
    client=EventClient(SECRET,session=Mock(post=post),sleep=Mock())
    client.append(experiment,events)
    assert len(saved)==1 and len(bodies)==2 and bodies[0]==bodies[1]
    assert next(iter(saved.values()))['received_at']=='2026-11-13T15:00:01+00:00'
