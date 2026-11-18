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
@pytest.mark.parametrize('notify',['off','success','failure'])
def test_paid_runner_exports_only_validated_reviews(tmp_path,monkeypatch,invalid,notify):
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
    if notify != 'off':
        import market_radar_ai.dashboard.fresh_notification as notification
        import market_radar_ai.dashboard.delivery_ledger as delivery
        env['SEND_FRESH_REVIEW']='true'
        monkeypatch.setattr(delivery,'GitHubDeliveryStore',lambda token:object())
        def deliver(*args,**kwargs):
            if notify=='failure':raise RuntimeError('secret')
            return {'state':'fresh_research_delivery_confirmed'}
        monkeypatch.setattr(notification,'deliver',deliver)
    root=tmp_path/'run'
    if invalid:
        with pytest.raises(RuntimeError):execute(root,env=env,clock=lambda:NOW)
        assert not (root/'dashboard-review.json').exists()
    else:
        assert execute(root,env=env,clock=lambda:NOW)['state']=='completed'
        exported=json.loads((root/'dashboard-review.json').read_text())
        assert len(exported['reviews'])==8 and not exported['trade_authorized']
        if notify != 'off':
            delivery=json.loads((root/'notification-delivery.json').read_text())
            assert delivery['state']==('blocked_or_unconfirmed' if notify=='failure' else 'fresh_research_delivery_confirmed')
            assert 'secret' not in json.dumps(delivery)
    assert (root/'budget-after.json').exists()


def test_early_provider_failure_still_records_no_trade(tmp_path, monkeypatch):
    import json
    import market_radar_ai.agents.github_plan_review as module
    def broken(): raise RuntimeError('sensitive_provider_detail')
    monkeypatch.setattr(module,'check',broken)
    root=tmp_path/'failed'
    with pytest.raises(RuntimeError):execute(root,env=BASE,clock=lambda:NOW)
    report=json.loads((root/'session-report.json').read_text())
    assert report['runner_state']=='blocked_or_failed'
    assert report['outcome']['net_pnl_eur'] is None
    assert 'sensitive_provider_detail' not in json.dumps(report)
