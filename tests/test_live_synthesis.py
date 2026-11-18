"""Offline synthetic disagreement tests; they do not evaluate live AI quality."""
import json
import pytest
from test_live_research import setup, NOW
from market_radar_ai.agents.live_research import run_research


@pytest.mark.parametrize('defect,code', [
    ('copy','copied_debate_rationale'),
    ('case_punctuation_copy','copied_debate_rationale'),
    ('unknown','decisive_concern_mismatch'),
    ('duplicate','decisive_concern_mismatch'),
    ('empty','decisive_concern_mismatch'),
    ('repeat_counter','repeated_counterargument'),
    ('repeat_next','duplicate_next_evidence'),
])
def test_final_synthesis_rejects_shortcuts(tmp_path,monkeypatch,defect,code):
    def mutate(data,payload):
        if 'rationale' not in data:return
        if defect=='copy':data['rationale']=payload['debate']['discussion']
        elif defect=='case_punctuation_copy':data['rationale']=payload['debate']['discussion'].upper().replace('.', '!')
        elif defect=='unknown':data['decisive_concern_ids']=['invented']
        elif defect=='duplicate':data['decisive_concern_ids']*=2
        elif defect=='empty':data['decisive_concern_ids']=[]
        elif defect=='repeat_counter':data['counterargument']=data['rationale']
        else:data['next_evidence']*=2
    packet,client,store,requests=setup(monkeypatch,mutate=mutate)
    path=tmp_path/'rejected.json'
    with pytest.raises(RuntimeError):run_research(client,packet,path=path,clock=lambda:NOW,enabled=True)
    report=json.loads(path.read_text())
    assert report['conclusion'] is None and report['trade_authorized'] is False
    assert report['calls'][-1]['validation_details'][0]['type']==code
    assert report['calls'][-1]['rejected_response']['status']=='untrusted_rejected_draft'
    assert len(requests)==8 and all(e['actual'] is not None for e in store.state['entries'].values())


def test_conflicting_specialists_keep_counterevidence_in_final_review(tmp_path,monkeypatch):
    def mutate(data,payload):
        role=data.get('role')
        if role=='opportunity_hunter':
            data.update(summary='A continuation hypothesis warrants further research.',
                        concerns=['Continuation has not been confirmed.'])
        if role=='devils_advocate':
            data.update(summary='A failed move remains a plausible alternative.',
                        concerns=['The apparent trend may be temporary noise.'])
        if 'discussion' in data:
            data['discussion']='Continuation and failure are competing interpretations. The evidence cannot resolve them.'
        if 'rationale' in data:
            data.update(verdict='INSUFFICIENT_EVIDENCE',
                decisive_concern_ids=['opportunity_hunter:1','devils_advocate:1'],
                rationale='The competing interpretations lack confirmation, so no directional conclusion is established.',
                counterargument='Continuation is plausible, but it does not eliminate the temporary noise explanation.',
                next_evidence=['Obtain an independently sourced longer candle history.'])
            assert any(c['id']=='devils_advocate:1' for c in payload['unresolved_concerns'])
    packet,client,store,requests=setup(monkeypatch,mutate=mutate)
    report=run_research(client,packet,path=tmp_path/'conflict.json',clock=lambda:NOW,enabled=True)
    assert report['state']=='completed' and not report['trade_authorized']
    assert report['conclusion']['verdict']=='INSUFFICIENT_EVIDENCE'
    assert 'devils_advocate:1' in report['conclusion']['decisive_concern_ids']
    assert all('assessments' not in json.loads(r['input']) for r in requests[:6])


def test_empty_concern_register_does_not_require_invented_objections(tmp_path,monkeypatch):
    def mutate(data,payload):
        if 'role' in data:data['concerns']=[]
    packet,client,store,requests=setup(monkeypatch,mutate=mutate)
    report=run_research(client,packet,path=tmp_path/'empty.json',clock=lambda:NOW,enabled=True)
    assert report['conclusion']['decisive_concern_ids']==[]
    assert report['conclusion']['acknowledged_missing_data']==list(packet.missing_data)
