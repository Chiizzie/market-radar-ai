from decimal import Decimal
import sqlite3
import pytest
from test_spending import NOW
from market_radar_ai.agents.spending import SpendingLedger
from market_radar_ai.agents.openai_pilot import OpenAIPilot, MODEL, usage_cost, strict_schema

SCHEMA = {'type':'object','properties':{'ok':{'type':'boolean'}}}


def client(tmp_path, **kwargs):
    ledger = SpendingLedger(tmp_path/'spend.db', 1000000,
                           monthly_limit_microeur=2000000, lifetime_limit_microeur=1000000)
    return OpenAIPilot(api_key='test-key', ledger=ledger, eur_per_usd='0.9', **kwargs)


def run(c):
    return c.call(prompt='Return ok true.', schema=SCHEMA, request_id='test', now=NOW)


def body(**changes):
    return dict({'id':'resp_test','model':MODEL,'status':'completed',
        'usage':{'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':200}},
        'output':[{'type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}]}, **changes)


def mock_response(monkeypatch, data, status=200):
    calls=[]
    class Response:
        status_code=status
        def json(self): return data
    def post(*args, **kwargs):
        calls.append((args,kwargs))
        return Response()
    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post', post)
    return calls


def test_disabled_by_default(tmp_path):
    with pytest.raises(ValueError, match='disabled'): client(tmp_path)


def test_usage_and_request_controls(tmp_path, monkeypatch):
    c=client(tmp_path, enabled=True)
    calls=mock_response(monkeypatch,body())
    result=run(c)
    assert result.data == {'ok':True}
    assert result.cost_usd == Decimal('0.001065')
    assert result.estimated_cost_microeur == 959
    kwargs=calls[0][1]
    assert kwargs['allow_redirects'] is False
    assert kwargs['timeout'] == (10,45)
    assert kwargs['json']['store'] is False
    assert kwargs['json']['max_output_tokens'] == 512
    assert 'tools' not in kwargs['json']
    with pytest.raises(ValueError, match='already reserved'): run(c)
    assert len(calls)==1


def test_timeout_is_redacted_and_budget_retained(tmp_path, monkeypatch):
    c=client(tmp_path, enabled=True)
    def fail(*args, **kwargs): raise TimeoutError('test-key secret provider body')
    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post', fail)
    with pytest.raises(RuntimeError) as exc: run(c)
    assert 'test-key' not in str(exc.value)
    with sqlite3.connect(c.ledger.path) as db:
        assert db.execute('SELECT actual FROM spend').fetchone()==(None,)


@pytest.mark.parametrize('changes', [dict(status='incomplete'),dict(output=[]),
    dict(model='unexpected'),dict(output=[{'type':'message','content':[{'type':'refusal'}]}])])
def test_unusable_output_still_settles_cost(tmp_path, monkeypatch, changes):
    c=client(tmp_path,enabled=True)
    mock_response(monkeypatch,body(**changes))
    with pytest.raises((RuntimeError,ValueError)): run(c)
    with sqlite3.connect(c.ledger.path) as db:
        assert db.execute('SELECT actual FROM spend').fetchone()==(959,)


@pytest.mark.parametrize('usage', [{}, {'input_tokens':True,'output_tokens':2},
    {'input_tokens':2,'output_tokens':-1},
    {'input_tokens':2,'output_tokens':1,'input_tokens_details':{'cached_tokens':3}}])
def test_missing_or_invalid_usage_keeps_reservation(tmp_path,monkeypatch,usage):
    c=client(tmp_path,enabled=True)
    mock_response(monkeypatch,body(usage=usage))
    with pytest.raises(RuntimeError,match='Unknown usage'): run(c)
    with sqlite3.connect(c.ledger.path) as db:
        assert db.execute('SELECT actual FROM spend').fetchone()==(None,)


def test_budget_blocks_network(tmp_path,monkeypatch):
    c=client(tmp_path,enabled=True)
    c.ledger.limit=0
    calls=mock_response(monkeypatch,body())
    with pytest.raises(RuntimeError,match='daily_spending_limit'): run(c)
    assert calls==[]


def test_strict_schema_does_not_mutate_original():
    original={'type':'object','properties':{'x':{'type':'string','default':'x'}}}
    result=strict_schema(original)
    assert result['required']==['x'] and result['additionalProperties'] is False
    assert 'default' not in result['properties']['x']
    assert original['properties']['x']['default']=='x'


def test_schema_failure_is_charged_and_usage_is_audited(tmp_path,monkeypatch):
    from jsonschema import ValidationError
    c=client(tmp_path,enabled=True)
    mock_response(monkeypatch,body(output=[{'type':'message','content':[
        {'type':'output_text','text':'{"ok":"not a boolean"}'}]}]))
    with pytest.raises(ValidationError): run(c)
    with sqlite3.connect(c.ledger.path) as db:
        assert db.execute('SELECT actual FROM spend').fetchone()==(959,)
        assert db.execute('SELECT cost_usd, eur_per_usd FROM openai_usage').fetchone()==('0.001065','0.9')
