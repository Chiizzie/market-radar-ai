import pytest
from market_radar_ai.agents.github_plan_review import mode_for, execute
from test_plan_review import data, NOW

BASE=dict(GITHUB_REPOSITORY='Chiizzie/market-radar-ai',GITHUB_REF='refs/heads/phase-1/market-data-layer',GITHUB_EVENT_NAME='push',GITHUB_RUN_ATTEMPT='1')

def test_paid_only_first_manual_attempt():
    assert mode_for(BASE)=='dry_run'
    with pytest.raises(ValueError):mode_for(dict(BASE,PLAN_REVIEW_MODE='paid'))
    manual=dict(BASE,PLAN_REVIEW_MODE='paid',GITHUB_EVENT_NAME='workflow_dispatch')
    assert mode_for(manual)=='paid'
    with pytest.raises(ValueError):mode_for(dict(manual,GITHUB_RUN_ATTEMPT='2'))
    with pytest.raises(ValueError):mode_for(dict(BASE,GITHUB_REPOSITORY='Chiizzie/market-radar'))


def test_dry_run_builds_packet_without_paid_client(tmp_path,monkeypatch):
    import market_radar_ai.agents.github_plan_review as module
    from market_radar_ai.market_data.admission import FxQuote
    c,cat,d=data()
    monkeypatch.setattr(module,'capture_calendar',lambda:None)
    monkeypatch.setattr(module,'check',lambda:cat)
    monkeypatch.setattr(module,'capture',lambda:c)
    class FX:
        def fetch(self,currency):return FxQuote.model_validate(d['fx_evidence'])
    monkeypatch.setattr(module,'YahooFxProvider',FX)
    monkeypatch.setattr(module,'OpenAIPilot',lambda **kw:pytest.fail('paid client in dry-run'))
    result=execute(tmp_path/'run',env=BASE,clock=lambda:NOW)
    assert result['state']=='ready_dry_run' and result['model_calls']==0
    assert (tmp_path/'run'/'packet.json').exists()
    with pytest.raises(ValueError):execute(tmp_path/'run',env=BASE)

@pytest.mark.parametrize('invalid',[False,True])
def test_paid_runner_exports_only_validated_reviews(tmp_path,monkeypatch,invalid):
    import json
    from types import SimpleNamespace
    import market_radar_ai.agents.github_plan_review as module
    from market_radar_ai.market_data.admission import FxQuote
    from test_review_export import bundle
    c,cat,d,audit=bundle()
    if invalid:audit['calls'][0]['untrusted_response']['rationale']='unfinished'
    monkeypatch.setattr(module,'capture_calendar',lambda:None)
    monkeypatch.setattr(module,'check',lambda:cat)
    monkeypatch.setattr(module,'capture',lambda:c)
    class FX:
        def fetch(self,currency):return FxQuote.model_validate(d['fx_evidence'])
    monkeypatch.setattr(module,'YahooFxProvider',FX)
    monkeypatch.setattr(module,'GitHubBudgetStore',lambda token:object())
    monkeypatch.setattr(module,'GitHubSpendingLedger',lambda store:SimpleNamespace(summary=lambda:{'test_only':True}))
    monkeypatch.setattr(module,'OpenAIPilot',lambda **kwargs:object())
    monkeypatch.setattr(module,'run_paid',lambda *args,**kwargs:audit)
    env=dict(BASE,GITHUB_EVENT_NAME='workflow_dispatch',PLAN_REVIEW_MODE='paid',OPENAI_API_KEY='fixture',GH_BUDGET_TOKEN='fixture')
    root=tmp_path/'run'
    if invalid:
        with pytest.raises(RuntimeError):execute(root,env=env,clock=lambda:NOW)
        assert not (root/'dashboard-review.json').exists()
    else:
        assert execute(root,env=env,clock=lambda:NOW)['state']=='completed'
        exported=json.loads((root/'dashboard-review.json').read_text())
        assert len(exported['reviews'])==8 and not exported['trade_authorized']
    assert (root/'budget-after.json').exists()
