from copy import deepcopy
from market_radar_ai.agents.qualification import qualify, paid_review_gate
from market_radar_ai.agents.candidate_packages import build_packages, digest
from test_candidate_packages import stock_capture, feed, NOW


def test_free_report_exposes_blockers_without_mutating_capture():
    capture = stock_capture(); original = deepcopy(capture)
    report = qualify(capture, feed(), now=NOW)
    assert capture == original
    assert report['shortlisted_count'] == 1
    assert report['paid_eligible_count'] == report['model_calls'] == 0
    assert 'catalogue_candidate_not_confirmed' in report['blocker_counts']
    assert not report['trade_authorized']


def test_clearing_labels_cannot_authorize_legacy_research():
    record = build_packages(stock_capture(), feed(), now=NOW)['packages'][0]
    record['package']['missing_evidence'] = []
    record['package']['plan'] = {'fake': True}
    record['package_id'] = digest(record['package'])
    gate = paid_review_gate(record, now=NOW)
    assert not gate['eligible_for_paid_review']
    assert 'legacy_research_package_not_a_paper_verdict' in gate['blockers']


def test_unqualified_scheduler_never_touches_budget_or_models(tmp_path, monkeypatch):
    import market_radar_ai.agents.scheduled_review as mod
    from test_scheduled_review import ENV
    batch = build_packages(stock_capture(), feed(), now=NOW)
    monkeypatch.setattr(mod, 'permitted', lambda *a: True)
    monkeypatch.setattr(mod, 'build_briefing', lambda *a, **k: {'packages': []})
    monkeypatch.setattr(mod, 'build_packages', lambda *a, **k: batch)
    def forbidden(*a, **k):
        raise AssertionError('Unqualified candidates must not touch paid infrastructure')
    monkeypatch.setattr(mod, 'GitHubBudgetStore', forbidden)
    monkeypatch.setattr(mod, 'OpenAIPilot', forbidden)
    result = mod.execute(stock_capture(), feed(), tmp_path/'run', env=ENV, clock=lambda:NOW)
    assert result['state'] == 'no_qualified_candidate_zero_cost'
    assert result['model_calls'] == 0


def test_free_qualification_checks_all_twenty_collected_stocks():
    from test_capture_shortlist import capture
    symbols=tuple('S'+str(i) for i in range(20))
    # Build valid independent symbol captures; the normal helper defaults to ten.
    doc=stock_capture();doc['captures']=[]
    for symbol in symbols:
        one=capture((symbol,))['captures'][0];one['market']='stocks'
        doc['captures'].append(one)
    doc['coverage']['stocks'].update(requested=20,attempted=20,successful=20,quality_passed=20,deferred=[])
    report=qualify(doc,feed(symbols),now=NOW)
    assert {r['symbol'] for r in report['candidates']}==set(symbols)
    assert report['selection']['markets']['stocks']['deferred_by_limit']==0
    assert report['model_calls']==0 and not report['trade_authorized']
