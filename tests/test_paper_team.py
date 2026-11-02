from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from market_radar_ai.agents.paper_team import ResearchInput, PaperPlan, PaperTeam, SimulatedAgent, UsageBudget
from market_radar_ai.agents.roles import AgentRole

NOW = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)


def snapshot(**changes):
    data = dict(candidate_id='fixture-1', symbol='TEST', observed_at=NOW,
                asset_class='equity', broker='trading212_invest',
                broker_verified_until=NOW+timedelta(hours=1), quality_passed=True,
                source_ids=('fixture',))
    data.update(changes)
    return ResearchInput(**data)


def plan(**changes):
    data = dict(entry=100, stop=99, target=102, quantity=10, costs_eur=1,
                invalidation='Fixture support fails', exit_by=NOW.replace(hour=22))
    data.update(changes)
    return PaperPlan(**data)


def agents():
    return [SimulatedAgent(role, stance='support', source='fixture') for role in AgentRole]


def test_full_six_role_flow_seven_calls_and_zero_cost():
    result = PaperTeam(agents()).run(snapshot(), now=NOW, plan=plan())
    assert result.verdict == 'PAPER_PLAN' and len(result.reports) == 6
    assert result.calls_used == 7 and result.cost_eur == 0 and result.simulated
    assert result.plan.planned_loss == Decimal(11)
    assert len({r.snapshot_id for r in result.reports}) == 1


def test_objection_survives_unanimous_support():
    team = agents()
    team[3] = SimulatedAgent(AgentRole.DEVILS_ADVOCATE, stance='support', source='fixture', objections=['Catalyst unverified'])
    result = PaperTeam(team).run(snapshot(), now=NOW, plan=plan())
    assert result.verdict == 'NO_ACTION' and result.plan is None
    assert result.debate[0].issue == 'Catalyst unverified'


@pytest.mark.parametrize('changes,reason', [
    ({'quality_passed': False}, 'data_quality_failed'),
    ({'observed_at': NOW-timedelta(hours=1)}, 'stale_or_future_snapshot'),
    ({'broker_verified_until': NOW}, 'broker_verification_expired'),
    ({'broker': 'robinhood_europe'}, 'broker_asset_mismatch'),
    ({'missing_data': ('news',)}, 'snapshot_missing_data'),
])
def test_invalid_input_never_invokes_agents(changes, reason):
    result = PaperTeam(agents()).run(snapshot(**changes), now=NOW, plan=plan())
    assert reason in result.failures and result.calls_used == 0


@pytest.mark.parametrize('changes,reason', [
    ({'quantity': 20, 'costs_eur': 1}, 'risk_ceiling'),
    ({'exit_by': NOW+timedelta(days=1)}, 'invalid_intraday_exit'),
    ({'exit_by': NOW}, 'invalid_intraday_exit'),
])
def test_final_hard_gates_override_support(changes, reason):
    result = PaperTeam(agents()).run(snapshot(), now=NOW, plan=plan(**changes))
    assert reason in result.failures and result.plan is None


def test_exact_risk_limit_and_exit_boundary():
    assert PaperTeam(agents()).run(snapshot(), now=NOW, plan=plan(quantity=19)).verdict == 'PAPER_PLAN'
    assert PaperTeam(agents()).run(snapshot(), now=NOW, plan=plan(exit_by=NOW.replace(hour=22,second=1))).verdict == 'NO_ACTION'


def test_budget_shared_across_candidates():
    budget = UsageBudget(max_calls=8)
    team = PaperTeam(agents(), budget=budget)
    assert team.run(snapshot(), now=NOW, plan=plan()).calls_used == 7
    result = team.run(snapshot(candidate_id='second'), now=NOW, plan=plan())
    assert budget.used == 8 and result.calls_used == 1 and result.verdict == 'NO_ACTION'


def test_no_budget_for_final_decision_blocks_plan():
    result = PaperTeam(agents(), budget=UsageBudget(6)).run(snapshot(), now=NOW, plan=plan())
    assert result.verdict == 'NO_ACTION' and len(result.reports) == 6


def test_unknown_sources_and_missing_evidence_rejected():
    team = agents()
    team[0] = SimulatedAgent(AgentRole.OPPORTUNITY_HUNTER, stance='support', source='invented')
    assert PaperTeam(team).run(snapshot(), now=NOW, plan=plan()).verdict == 'NO_ACTION'
    team[0] = SimulatedAgent(AgentRole.OPPORTUNITY_HUNTER, stance='support')
    assert PaperTeam(team).run(snapshot(), now=NOW, plan=plan()).debate


def test_duplicate_roles_and_paid_adapters_rejected():
    with pytest.raises(ValueError): PaperTeam([agents()[0]]*6)
    class Paid(SimulatedAgent): pass
    team = agents()
    team[0] = Paid(AgentRole.OPPORTUNITY_HUNTER)
    with pytest.raises(ValueError): PaperTeam(team)


def test_deep_immutability_and_plan_validation():
    item = snapshot(source_ids=['fixture'])
    assert isinstance(item.source_ids, tuple)
    with pytest.raises(ValidationError): item.symbol = 'CHANGED'
    for change in ({'stop': 101}, {'entry': 'NaN'}, {'direction': 'SHORT'}):
        with pytest.raises(ValidationError): plan(**change)


def test_dublin_summer_cutoff():
    now = datetime(2026, 7, 1, 21, tzinfo=timezone.utc)
    result = PaperTeam(agents()).run(snapshot(observed_at=now, broker_verified_until=now+timedelta(hours=1)), now=now)
    assert 'entry_cutoff' in result.failures and result.calls_used == 0


def test_default_demo_rejects_and_supported_demo_is_explicit_simulation():
    from market_radar_ai.agents.demo import demo
    assert demo().verdict == 'NO_ACTION'
    result = demo('supported')
    assert result.verdict == 'PAPER_PLAN' and result.simulated and result.cost_eur == 0


def test_handoff_revalidates_admission():
    from market_radar_ai.pipeline import prepare_research
    from market_radar_ai.market_data.screening import ScreeningInput
    from market_radar_ai.market_data.models import Instrument, ProviderResult
    item = ScreeningInput(Instrument(symbol='ABC', asset_class='equity', quote_currency='EUR', venue='test'), ProviderResult(provider='test', retrieved_at=NOW))
    with pytest.raises(ValueError, match='broker_unverified'):
        prepare_research(item, candidate_id='bad', now=NOW)
