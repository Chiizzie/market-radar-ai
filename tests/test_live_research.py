from datetime import timedelta
from decimal import Decimal
import json
import pytest
from test_combined_input import capture
from test_news_input import feed, NOW
from test_github_budget import MemoryStore
from market_radar_ai.agents.combined_input import build_combined_input
from market_radar_ai.agents.live_research import run_research
from market_radar_ai.agents.openai_pilot import OpenAIPilot, MODEL
from market_radar_ai.agents.github_budget import GitHubSpendingLedger


def setup(monkeypatch, wrong_citation=False, fail=False):
    packet=build_combined_input(capture(),feed(),symbol='NVDA',now=NOW)
    store=MemoryStore()
    client=OpenAIPilot(api_key='test-only',ledger=GitHubSpendingLedger(store),eur_per_usd=1,enabled=True)
    requests=[]
    def post(url,**kwargs):
        requests.append(kwargs['json'])
        if fail:raise RuntimeError('secret provider text')
        payload=json.loads(kwargs['json']['input'])
        data={'snapshot_id':packet.digest(),'source_ids':['invented'] if wrong_citation else [packet.source_ids[0]]}
        if 'role' in payload:data.update(role=payload['role'],summary='Fixture assessment',concerns=['Broker remains unverified'])
        elif 'debate' in payload:data.update(verdict='MORE_RESEARCH_NEEDED',rationale='No plan authorized')
        else:data.update(discussion='Unresolved evidence remains')
        class Response:
            status_code=200
            def json(self):return {'model':MODEL,'id':f'resp-{len(requests)}','status':'completed',
                'usage':{'input_tokens':100,'output_tokens':100},
                'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(data)}]}]}
        return Response()
    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post',post)
    return packet,client,store,requests


def test_complete_metered_protocol_is_eight_calls_and_research_only(tmp_path,monkeypatch):
    packet,client,store,requests=setup(monkeypatch)
    report=run_research(client,packet,path=tmp_path/'result.json',clock=lambda:NOW,enabled=True)
    assert report['state']=='completed' and len(requests)==8
    assert len(report['unresolved_concerns'])==6 and not report['trade_authorized']
    assert all('assessments' not in json.loads(r['input']) for r in requests[:6])
    assert all(e['actual'] is not None for e in store.state['entries'].values())
    assert all(c['state']=='validated' for c in report['calls'])
    with pytest.raises(RuntimeError):run_research(client,packet,path=tmp_path/'duplicate.json',clock=lambda:NOW,enabled=True)
    assert len(requests)==8  # ledger rejects before HTTP


def test_disabled_or_stale_packet_spends_nothing(tmp_path,monkeypatch):
    packet,client,store,requests=setup(monkeypatch)
    with pytest.raises(ValueError):run_research(client,packet,path=tmp_path/'off.json',clock=lambda:NOW)
    with pytest.raises(RuntimeError):run_research(client,packet,path=tmp_path/'stale.json',clock=lambda:NOW+timedelta(hours=1),enabled=True)
    assert not requests and not store.state['entries']


def test_midrun_expiry_stops_before_next_reservation(tmp_path,monkeypatch):
    packet,client,store,requests=setup(monkeypatch)
    times=iter([NOW,NOW,NOW+timedelta(hours=1)])
    with pytest.raises(RuntimeError):run_research(client,packet,path=tmp_path/'expired.json',clock=lambda:next(times),enabled=True)
    assert len(requests)==1 and len(store.state['entries'])==1


def test_bad_citation_keeps_usage_and_stops(tmp_path,monkeypatch):
    packet,client,store,requests=setup(monkeypatch,wrong_citation=True)
    path=tmp_path/'invalid.json'
    with pytest.raises(RuntimeError):run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    report=json.loads(path.read_text())
    assert report['state']=='blocked_or_failed' and len(requests)==1
    assert report['calls'][0]['state']=='received'
    assert next(iter(store.state['entries'].values()))['actual'] is not None


def test_provider_failure_retains_hold_and_does_not_retry(tmp_path,monkeypatch):
    packet,client,store,requests=setup(monkeypatch,fail=True)
    path=tmp_path/'failed.json'
    with pytest.raises(RuntimeError):run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    assert len(requests)==1 and next(iter(store.state['entries'].values()))['actual'] is None
    assert 'secret provider text' not in path.read_text()


def test_existing_report_is_not_overwritten(tmp_path,monkeypatch):
    packet,client,store,requests=setup(monkeypatch)
    path=tmp_path/'existing.json';path.write_text('preserve prior audit')
    with pytest.raises(ValueError):run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    assert path.read_text()=='preserve prior audit' and not requests
