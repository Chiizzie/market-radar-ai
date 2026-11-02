from datetime import timedelta
from types import SimpleNamespace
from decimal import Decimal
import json
import pytest
from test_combined_input import capture
from test_news_input import feed, NOW
from test_github_budget import MemoryStore
from market_radar_ai.agents import github_live_research as runner
ENV={'GITHUB_REPOSITORY':'Chiizzie/market-radar-ai',
     'GITHUB_REF':'refs/heads/phase-1/market-data-layer',
     'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_RUN_ATTEMPT':'1'}


def public_data(monkeypatch):
    monkeypatch.setattr(runner,'capture_markets',lambda *a,**kw:capture())
    monkeypatch.setattr(runner,'fetch_feed',lambda **kw:feed())


def forbid_paid(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('Paid dependency must not be reached')
    for name in ('GitHubBudgetStore','OpenAIPilot','YahooFxProvider','run_research'):
        monkeypatch.setattr(runner,name,forbidden)


def test_default_dry_run_uses_no_credentials_or_paid_dependencies(tmp_path,monkeypatch):
    public_data(monkeypatch);forbid_paid(monkeypatch)
    result=runner.execute(tmp_path,env=ENV,clock=lambda:NOW)
    assert result['state']=='ready_dry_run' and result['model_calls']==0
    assert json.loads((tmp_path/'input.json').read_text())['trade_authorized'] is False


@pytest.mark.parametrize('change',[{'GITHUB_REPOSITORY':'Chiizzie/market-radar'},
    {'GITHUB_REF':'refs/heads/main'},{'GITHUB_EVENT_NAME':'push'},
    {'LIVE_RESEARCH_MODE':'paid'},
    {'LIVE_RESEARCH_MODE':'paid','ENABLE_LIVE_RESEARCH':'enabled','GITHUB_RUN_ATTEMPT':'2'}])
def test_activation_gate_precedes_provider_calls(tmp_path,monkeypatch,change):
    def forbidden(*a,**kw):pytest.fail('Gate must precede provider calls')
    monkeypatch.setattr(runner,'capture_markets',forbidden)
    with pytest.raises(ValueError):runner.execute(tmp_path,env={**ENV,**change},clock=lambda:NOW)


def test_stale_evidence_stops_before_ledger_or_paid_client(tmp_path,monkeypatch):
    public_data(monkeypatch);forbid_paid(monkeypatch)
    env={**ENV,'LIVE_RESEARCH_MODE':'paid','ENABLE_LIVE_RESEARCH':'enabled'}
    with pytest.raises(RuntimeError):runner.execute(tmp_path,env=env,clock=lambda:NOW+timedelta(hours=1))
    report=json.loads((tmp_path/'status.json').read_text())
    assert report['state']=='blocked_or_failed' and not (tmp_path/'analysis.json').exists()


def test_opted_in_path_uses_shared_ledger_and_cost_fx(tmp_path,monkeypatch):
    public_data(monkeypatch)
    store=MemoryStore()
    monkeypatch.setattr(runner,'GitHubBudgetStore',lambda token:store)
    monkeypatch.setattr(runner,'YahooFxProvider',lambda:SimpleNamespace(fetch=lambda *a,**kw:
        SimpleNamespace(eur_per_unit=Decimal('.9'),observed_at=NOW,source='fixture')))
    calls=[]
    def research(client,packet,**kwargs):
        calls.append(client)
        assert client.ledger.store is store and client.rate==Decimal('.9')
        assert kwargs['enabled'] is True
        return {'state':'completed','calls':[{}]*8}
    monkeypatch.setattr(runner,'run_research',research)
    env={**ENV,'LIVE_RESEARCH_MODE':'paid','ENABLE_LIVE_RESEARCH':'enabled',
         'OPENAI_API_KEY':'test-not-real','GH_BUDGET_TOKEN':'test'}
    result=runner.execute(tmp_path,env=env,clock=lambda:NOW)
    assert result['model_calls']==8 and len(calls)==1
    assert (tmp_path/'budget-before.json').exists() and (tmp_path/'budget-after.json').exists()
    assert 'test-not-real' not in ''.join(p.read_text() for p in tmp_path.glob('*.json'))


def test_existing_run_preserved(tmp_path,monkeypatch):
    (tmp_path/'status.json').write_text('existing')
    with pytest.raises(ValueError):runner.execute(tmp_path,env=ENV,clock=lambda:NOW)
    assert (tmp_path/'status.json').read_text()=='existing'
