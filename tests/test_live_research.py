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


def setup(monkeypatch, wrong_citation=False, fail=False, mutate=None, packet_override=None):
    packet=packet_override or build_combined_input(capture(),feed(),symbol='NVDA',now=NOW)
    store=MemoryStore()
    client=OpenAIPilot(api_key='test-only',ledger=GitHubSpendingLedger(store),eur_per_usd=1,enabled=True)
    requests=[]
    def post(url,**kwargs):
        requests.append(kwargs['json'])
        if fail:raise RuntimeError('secret provider text')
        payload=json.loads(kwargs['json']['input'])
        data={'metric_claims':[], 'execution_quality':'UNKNOWN_NO_SPREAD_OR_DEPTH','snapshot_id':packet.digest(),'source_ids':['invented'] if wrong_citation else [packet.source_ids[0]]}
        if 'role' in payload:data.update(role=payload['role'],summary='Fixture assessment.',concerns=['Broker remains unverified.'])
        elif 'debate' in payload:data.update(verdict='MORE_RESEARCH_NEEDED',rationale='No plan authorized.')
        else:data.update(discussion='Unresolved evidence remains.')
        if mutate:mutate(data,payload)
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


@pytest.mark.parametrize('bad_summary', [
    'The range remains uncertain but the',
    'The window high is 68,914.9.',
    'Liquidity appears adequate.',
    'Spreads are tight.',
    'The range is uncertain…',
    'Unclear expansion in参与/',
])
def test_rejected_prose_stops_paid_pipeline_and_preserves_cost(tmp_path,monkeypatch,bad_summary):
    packet,client,store,requests=setup(monkeypatch,mutate=lambda d,p:d.update(summary=bad_summary))
    path=tmp_path/'rejected.json'
    with pytest.raises(RuntimeError):
        run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    report=json.loads(path.read_text())
    assert len(requests)==1 and report['state']=='blocked_or_failed'
    assert report['calls'][0]['state']=='rejected'
    assert report['calls'][0]['estimated_cost_microeur'] > 0
    assert next(iter(store.state['entries'].values()))['actual'] is not None
    assert not report['assessments'] and report['debate'] is None
    assert not report['trade_authorized']


def test_recorded_crypto_high_and_real_truncated_summaries():
    from pathlib import Path
    from market_radar_ai.agents.crypto_input import CryptoResearchInput
    from market_radar_ai.agents.live_research import market_metrics, validate_claims, ResearchAssessment, checked_prose
    fixture=json.loads((Path(__file__).parent/'fixtures/live_crypto_trial.json').read_text())
    packet=CryptoResearchInput.model_validate(fixture['input'])
    metrics=market_metrics(packet)
    assert Decimal(metrics['window_high']) == Decimal('68961.8')
    assert Decimal(metrics['window_low']) == Decimal('68426.1')
    base=dict(role=fixture['assessments'][0]['role'],snapshot_id=packet.digest(),
        summary='The evidence is limited.',concerns=[],source_ids=[packet.market.source_id()],
        execution_quality='UNKNOWN_NO_SPREAD_OR_DEPTH')
    claim=dict(metric='window_high',value='68914.9',quote_currency='EUR',source_id=packet.market.source_id())
    with pytest.raises(ValueError,match='metric_mismatch'):
        validate_claims(ResearchAssessment(**base,metric_claims=[claim]),packet,metrics)
    claim['value']='68961.800'
    validate_claims(ResearchAssessment(**base,metric_claims=[claim]),packet,metrics)
    for original in fixture['assessments']:
        if len(original['summary'])==600:
            with pytest.raises(ValueError):checked_prose(original['summary'])


@pytest.mark.parametrize('change', [
    {'value':'999999'}, {'quote_currency':'EUR'}, {'source_id':'invented'},
])
def test_bad_structured_claim_is_rejected_after_settlement(tmp_path,monkeypatch,change):
    def mutate(data,payload):
        metrics=payload['computed_metrics']
        data['source_ids']=[metrics['source_id']]
        data['metric_claims']=[dict(metric='window_high',value=metrics['values']['window_high'],
            quote_currency=metrics['quote_currency'],source_id=metrics['source_id']) | change]
    packet,client,store,requests=setup(monkeypatch,mutate=mutate)
    with pytest.raises(RuntimeError):
        run_research(client,packet,path=tmp_path/'bad.json',clock=lambda:NOW,enabled=True)
    assert len(requests)==1 and next(iter(store.state['entries'].values()))['actual'] is not None


def test_valid_claims_are_available_to_all_stages(tmp_path,monkeypatch):
    def mutate(data,payload):
        metrics=payload['computed_metrics']
        data['source_ids']=[metrics['source_id']]
        data['metric_claims']=[dict(metric='window_high',value=metrics['values']['window_high'],
            quote_currency=metrics['quote_currency'],source_id=metrics['source_id'])]
    packet,client,store,requests=setup(monkeypatch,mutate=mutate)
    report=run_research(client,packet,path=tmp_path/'good.json',clock=lambda:NOW,enabled=True)
    assert len(requests)==8 and report['state']=='completed'
    assert report['analysis_quality']=='requires_human_review'
    assert all(json.loads(r['input'])['computed_metrics']==report['computed_metrics'] for r in requests)


@pytest.mark.parametrize('field,value', [
    ('concerns',['x'*241+'.']), ('concerns',["One concern','another concern."]),
    ('execution_quality','ADEQUATE'), ('summary','A'*501+'.'),
])
def test_bounded_structured_response(field,value,tmp_path,monkeypatch):
    packet,client,store,requests=setup(monkeypatch,mutate=lambda d,p:d.update({field:value}))
    with pytest.raises(RuntimeError):
        run_research(client,packet,path=tmp_path/'bad.json',clock=lambda:NOW,enabled=True)
    assert len(requests)==1


@pytest.mark.parametrize('stage,expected_calls', [('debate',7),('conclusion',8)])
def test_peer_stages_use_same_quality_gate(tmp_path,monkeypatch,stage,expected_calls):
    def mutate(data,payload):
        if stage=='debate' and 'discussion' in data:data['discussion']='Window high is 68914.9.'
        if stage=='conclusion' and 'rationale' in data:data['rationale']='Missing evidence but the'
    packet,client,store,requests=setup(monkeypatch,mutate=mutate)
    path=tmp_path/'peer.json'
    with pytest.raises(RuntimeError):run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    report=json.loads(path.read_text())
    assert len(requests)==expected_calls and report['conclusion'] is None
    assert report['calls'][-1]['state']=='rejected'
    assert all(e['actual'] is not None for e in store.state['entries'].values())


def test_rejection_diagnostics_quarantine_draft_without_forwarding(tmp_path,monkeypatch):
    bad='Incomplete summary'
    packet,client,store,requests=setup(monkeypatch,mutate=lambda d,p:d.update(summary=bad))
    path=tmp_path/'diagnostic.json'
    with pytest.raises(RuntimeError):run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    report=json.loads(path.read_text());call=report['calls'][0]
    assert call['validation_details']==[{'field':['summary'],'type':'value_error'}]
    assert call['rejected_response']['data']['summary']==bad
    assert call['rejected_response']['status']=='untrusted_rejected_draft'
    assert call['rejected_response']['trade_authorized'] is False
    assert report['assessments']==[] and report['debate'] is None and len(requests)==1


def test_oversized_rejected_draft_is_not_retained(tmp_path,monkeypatch):
    from dataclasses import replace
    packet,client,store,requests=setup(monkeypatch)
    original=client.call
    def oversized(**kwargs):
        reply=original(**kwargs)
        return replace(reply,data={**reply.data,'summary':'x'*33000})
    monkeypatch.setattr(client,'call',oversized)
    path=tmp_path/'oversized.json'
    with pytest.raises(RuntimeError):run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    call=json.loads(path.read_text())['calls'][0]
    assert call['rejected_response']['data'] is None
    assert call['rejected_response']['omitted_for_size'] is True
    assert call['validation_details'][0]['field']==['summary']
