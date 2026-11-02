"""Deterministic research gates. Models cannot waive mandatory constraints."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import AwareDatetime, Field, StrictBool
from .paper_team import Frozen, PaperPlan


class PolicyFacts(Frozen):
    asset_class: Literal['equity','crypto']
    broker: Literal['trading212_invest','robinhood_europe']
    broker_verified: StrictBool
    broker_verified_until: AwareDatetime
    observed_at: AwareDatetime
    currency: str
    completed_candles: StrictBool
    plan: PaperPlan


def mandatory_blocks(facts: PolicyFacts, now: datetime):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Aware evaluation clock required')
    local=now.astimezone(ZoneInfo('Europe/Dublin'))
    exit_at=facts.plan.exit_by.astimezone(ZoneInfo('Europe/Dublin'))
    blocks=[]
    expected='trading212_invest' if facts.asset_class=='equity' else 'robinhood_europe'
    if not facts.broker_verified or facts.broker!=expected: blocks.append('broker_unverified')
    if facts.broker_verified_until<=now: blocks.append('broker_expired')
    if not facts.completed_candles or not 0 <= (now-facts.observed_at).total_seconds() <= 600:
        blocks.append('stale_or_incomplete_data')
    if facts.currency!='EUR': blocks.append('currency_mismatch')
    if facts.plan.planned_loss>Decimal('20'): blocks.append('excess_planned_risk')
    if (local.hour>=22 or exit_at<=local or exit_at.date()!=local.date()
            or exit_at>exit_at.replace(hour=22,minute=0,second=0,microsecond=0)):
        blocks.append('time_rule')
    return blocks


IssueCode=Literal['broker_unverified','broker_expired','stale_or_incomplete_data',
    'currency_mismatch','excess_planned_risk','time_rule','material_evidence_gap','routine_uncertainty']


def issue_severity(code):
    # Only ordinary uncertainty is a caution. Unknown values fail closed.
    if code=='routine_uncertainty': return 'caution'
    if code in {'broker_unverified','broker_expired','stale_or_incomplete_data',
                'currency_mismatch','excess_planned_risk','time_rule','material_evidence_gap'}:
        return 'blocker'
    raise ValueError('Unknown issue category')
