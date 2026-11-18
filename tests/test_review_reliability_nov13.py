from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from market_radar_ai.agents.github_budget import GitHubBudgetStore, GitHubSpendingLedger, BudgetWriteError, initial_state
from market_radar_ai.agents.openai_pilot import OpenAIPilot, IncompleteModelResponse
from test_github_budget import MemoryStore
from test_spending import NOW


def test_confirmed_throttle_retries_identical_cas_without_losing_holds(monkeypatch):
    state=initial_state()
    state['entries']['existing']={'day':NOW.date().isoformat(),'reserved':500,'actual':None,'usage':None}
    sent=[];waits=[]
    def put(*a,**kw):
        sent.append(deepcopy(kw))
        return SimpleNamespace(status_code=403 if len(sent)==1 else 200,
            headers={'retry-after':'2'},json=lambda:{'message':'secondary rate limit TOKEN'})
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put',put)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.time.sleep',waits.append)
    store=GitHubBudgetStore('TOKEN');store.save(state,'a'*40)
    loaded,_=store.load()
    assert loaded==state and sent[0]==sent[1] and waits==[2]


@pytest.mark.parametrize('status,headers,message,reason',[
    (403,{},'private repo TOKEN','forbidden_unclassified'),
    (403,{'Retry-After':'60'},'secondary rate limit TOKEN','rate_limited'),
    (429,{},'rate limit','rate_limited'),
    (500,{},'TOKEN','http_refusal'),
])
def test_long_or_unclassified_refusals_never_repeat_write(monkeypatch,status,headers,message,reason):
    sent=[]
    def put(*a,**kw):
        sent.append(kw);return SimpleNamespace(status_code=status,headers=headers,json=lambda:{'message':message})
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put',put)
    with pytest.raises(BudgetWriteError) as caught:GitHubBudgetStore('TOKEN').save(initial_state(),'a'*40)
    assert len(sent)==1 and caught.value.diagnostic['reason']==reason
    assert 'TOKEN' not in str(caught.value) and 'TOKEN' not in json.dumps(caught.value.diagnostic)


def test_lost_write_acknowledgement_is_never_retried(monkeypatch):
    import requests
    sent=[]
    def put(*a,**kw):sent.append(kw);raise requests.Timeout('TOKEN')
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put',put)
    with pytest.raises(BudgetWriteError,match='acceptance_unknown'):
        GitHubBudgetStore('TOKEN').save(initial_state(),'a'*40)
    assert len(sent)==1


def test_marker_claim_is_one_write_and_cannot_claim_duplicate():
    store=MemoryStore();ledger=GitHubSpendingLedger(store)
    ledger.claim_markers(('cooldown','attempt'),NOW)
    assert store.version==1 and ledger.summary()['held_microeur']==0
    assert set(store.state['entries'])=={'cooldown','attempt'}
    with pytest.raises(ValueError,match='already reserved'):ledger.claim_markers(('cooldown','new'),NOW)
    assert 'new' not in store.state['entries']


def test_compact_ledger_preserves_all_records_below_the_unchanged_cap(monkeypatch):
    import base64
    state=initial_state()
    for i in range(1900):
        state['entries'][f'paper-cooldown-v1:{i:064x}:1794585600']={
            'day':'2026-11-13','reserved':1,'actual':0,'usage':None}
    # All identities and amounts survive; no historical deletion or cap raise.
    before=json.dumps(state,sort_keys=True,indent=2).encode()
    sent=[]
    def put(*a,**kw):sent.append(kw['json']);return SimpleNamespace(status_code=200)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put',put)
    GitHubBudgetStore('test').save(state,'a'*40)
    raw=base64.b64decode(sent[0]['content'])
    assert len(raw)<len(before) and len(raw)<500000 and json.loads(raw)==state


def test_incomplete_provider_output_is_settled_and_never_parsed(tmp_path,monkeypatch):
    from test_openai_pilot import body,mock_response,SCHEMA
    store=MemoryStore();pilot=OpenAIPilot(api_key='test',ledger=GitHubSpendingLedger(store),eur_per_usd='0.9',enabled=True,
                                       receipt_directory=tmp_path/'receipts')
    requests=mock_response(monkeypatch,body(status='incomplete',incomplete_details={'reason':'max_output_tokens'},
        output=[{'type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}]))
    with pytest.raises(IncompleteModelResponse) as caught:
        pilot.call(prompt='test',schema=SCHEMA,request_id='test',now=NOW)
    assert caught.value.reason=='max_output_tokens'
    assert store.state['entries']['test']['actual']==959 and len(requests)==1
    assert len(list((tmp_path/'receipts').glob('*.json')))==1


def test_pipeline_incomplete_keeps_failure_visible_and_never_delivers(tmp_path,monkeypatch):
    from test_paper_verdict import fixture
    from market_radar_ai.agents.paper_verdict import run_pipeline
    fixture(monkeypatch)
    client=OpenAIPilot(api_key='fake',ledger=GitHubSpendingLedger(MemoryStore()),eur_per_usd='0.9',enabled=True)
    def fail(**kw):raise IncompleteModelResponse('max_output_tokens',{'input_tokens':10,'output_tokens':1024},100)
    monkeypatch.setattr(client,'call',fail)
    def forbidden(*a,**k):pytest.fail('Incomplete team must not refresh or deliver an approval')
    result=run_pipeline({},None,client=client,root=tmp_path/'run',refresh=forbidden,deliver=forbidden,clock=lambda:NOW,enabled=True)
    assert result['state']=='review_incomplete' and result['requires_attention'] and result['automatic_paid_retry'] is False
    assert not (tmp_path/'run'/'decision.json').exists()
    audit=json.loads((tmp_path/'run'/'review.json').read_text())
    assert audit['calls'][0]['failure']['reason']=='max_output_tokens' and audit['result'] is None
