"""Deterministic fictional demo; zero network calls, zero AI spend, no orders."""
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .paper_team import PaperTeam, SimulatedAgent, ResearchInput, PaperPlan
from .roles import AgentRole


def demo(scenario='objection'):
    now = datetime(2026, 11, 2, 15, tzinfo=ZoneInfo('Europe/Dublin'))
    snapshot = ResearchInput(candidate_id='SIMULATED-FIXTURE', symbol='FICTIONAL',
        observed_at=now, asset_class='equity', broker='trading212_invest',
        broker_verified_until=now+timedelta(hours=1), quality_passed=True,
        source_ids=('synthetic-fixture',), facts=('Fictional test data only',))
    agents = [SimulatedAgent(role, stance='support', source='synthetic-fixture',
        objections=('Catalyst has not been verified',) if scenario == 'objection' and role == AgentRole.DEVILS_ADVOCATE else ())
        for role in AgentRole]
    plan = PaperPlan(entry=100, stop=99, target=102, quantity=10, costs_eur=1,
                     invalidation='Fictional support breaks', exit_by=now.replace(hour=22))
    return PaperTeam(agents).run(snapshot, now=now, plan=plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['objection', 'supported'], default='objection')
    args = parser.parse_args()
    print(demo(args.scenario).model_dump_json(indent=2))


if __name__ == '__main__':
    main()
