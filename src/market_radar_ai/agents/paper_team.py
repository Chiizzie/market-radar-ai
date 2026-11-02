"""Six-role deterministic simulation. No model SDK, network call or order API."""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from .roles import AgentRole


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class ResearchInput(Frozen):
    candidate_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    observed_at: AwareDatetime
    asset_class: Literal['equity', 'crypto']
    broker: Literal['trading212_invest', 'robinhood_europe']
    broker_verified_until: AwareDatetime
    quality_passed: bool
    currency: Literal['EUR'] = 'EUR'
    source_ids: tuple[str, ...] = Field(min_length=1)
    facts: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()

    def digest(self):
        return sha256(self.model_dump_json().encode()).hexdigest()


class PaperPlan(Frozen):
    direction: Literal['LONG'] = 'LONG'
    entry: Decimal = Field(gt=0, allow_inf_nan=False)
    stop: Decimal = Field(gt=0, allow_inf_nan=False)
    target: Decimal = Field(gt=0, allow_inf_nan=False)
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    costs_eur: Decimal = Field(ge=0, allow_inf_nan=False)
    invalidation: str = Field(min_length=1)
    exit_by: AwareDatetime

    @model_validator(mode='after')
    def ordered_levels(self):
        if not self.stop < self.entry < self.target:
            raise ValueError('Long plan requires stop < entry < target')
        return self

    @property
    def planned_loss(self):
        return (self.entry - self.stop) * self.quantity + self.costs_eur


class Finding(Frozen):
    claim: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


class RoleReport(Frozen):
    role: AgentRole
    snapshot_id: str
    stance: Literal['support', 'oppose', 'abstain']
    rationale: str = Field(min_length=1)
    findings: tuple[Finding, ...] = ()
    objections: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()
    simulated: Literal[True] = True


class DebateItem(Frozen):
    raised_by: AgentRole
    issue: str
    status: Literal['unresolved'] = 'unresolved'


class TeamResult(Frozen):
    candidate_id: str
    snapshot_id: str
    decided_at: AwareDatetime
    reports: tuple[RoleReport, ...]
    debate: tuple[DebateItem, ...]
    verdict: Literal['PAPER_PLAN', 'NO_ACTION']
    failures: tuple[str, ...]
    plan: PaperPlan | None = None
    calls_used: int
    cost_eur: Decimal = Decimal(0)
    simulated: Literal[True] = True


class SimulatedAgent:
    """A scripted role response, explicitly not independent AI intelligence."""
    def __init__(self, role, *, stance='abstain', objections=(), missing_data=(), source=None):
        self.role = AgentRole(role)
        self.stance, self.objections, self.missing_data, self.source = stance, tuple(objections), tuple(missing_data), source

    def analyse(self, snapshot: ResearchInput) -> RoleReport:
        findings = () if self.source is None else (Finding(claim='Scripted fixture evidence', source_id=self.source),)
        return RoleReport(role=self.role, snapshot_id=snapshot.digest(), stance=self.stance,
                          rationale=f'Simulated {self.role.value} assessment; not a live recommendation.',
                          findings=findings, objections=self.objections, missing_data=self.missing_data)


    def adjudicate(self, reports, debate):
        if self.role != AgentRole.FINAL_DECISION:
            raise ValueError('Only the decision role can adjudicate')
        return len(reports) == 6 and not debate and all(r.stance == 'support' for r in reports)


class UsageBudget:
    """Shared across runs. Reserves calls before invocation, including failed calls.

    Costs are always zero here. A paid adapter requires a separate monetary/token
    reservation implementation and explicit activation; it cannot be injected here.
    """
    def __init__(self, max_calls=100):
        if max_calls < 1: raise ValueError('max_calls must be positive')
        self.max_calls, self.used = max_calls, 0

    def reserve(self):
        if self.used >= self.max_calls: raise RuntimeError('call_budget_exhausted')
        self.used += 1


class PaperTeam:
    def __init__(self, agents, *, budget=None):
        if len(agents) != 6 or {a.role for a in agents} != set(AgentRole):
            raise ValueError('Exactly one agent per each of the six roles is required')
        if any(type(a) is not SimulatedAgent for a in agents):
            raise ValueError('Only simulated agents are enabled')
        self.agents = tuple(agents)
        self.budget = budget or UsageBudget()

    def run(self, snapshot: ResearchInput, *, now: datetime, plan: PaperPlan | None = None):
        if now.tzinfo is None: raise ValueError('now must be timezone-aware')
        # Revalidate inputs even if callers constructed them without normal validation.
        snapshot = ResearchInput.model_validate(snapshot.model_dump())
        if plan is not None: plan = PaperPlan.model_validate(plan.model_dump())
        digest, reports, debate, failures = snapshot.digest(), [], [], []
        initial_calls = self.budget.used
        if not snapshot.quality_passed: failures.append('data_quality_failed')
        if not 0 <= (now-snapshot.observed_at).total_seconds() <= 600: failures.append('stale_or_future_snapshot')
        if snapshot.broker_verified_until <= now: failures.append('broker_verification_expired')
        expected = 'trading212_invest' if snapshot.asset_class == 'equity' else 'robinhood_europe'
        if snapshot.broker != expected: failures.append('broker_asset_mismatch')
        local = now.astimezone(ZoneInfo('Europe/Dublin'))
        if local.hour >= 22: failures.append('entry_cutoff')
        if snapshot.missing_data: failures.append('snapshot_missing_data')
        if plan is None:
            failures.append('missing_plan')
        else:
            exit_local = plan.exit_by.astimezone(ZoneInfo('Europe/Dublin'))
            if plan.planned_loss > Decimal('20'): failures.append('risk_ceiling')
            if not (now < plan.exit_by and exit_local.date() == local.date()
                    and (exit_local.hour, exit_local.minute, exit_local.second, exit_local.microsecond) <= (22, 0, 0, 0)):
                failures.append('invalid_intraday_exit')
        if not failures:
            for agent in self.agents:
                try:
                    self.budget.reserve()
                    # Each receives only a fresh immutable snapshot, never peer output.
                    report = RoleReport.model_validate(agent.analyse(snapshot.model_copy(deep=True)).model_dump())
                    if report.role != agent.role or report.snapshot_id != digest:
                        raise ValueError('report_identity_mismatch')
                    if any(f.source_id not in snapshot.source_ids for f in report.findings):
                        raise ValueError('unknown_evidence_source')
                    reports.append(report)
                except Exception:
                    failures.append('agent_failure_or_budget_exhausted')
                    break
        if len(reports) == 6:
            # Debate is assembled only after every independent first pass exists.
            for report in reports:
                for issue in report.objections + report.missing_data:
                    debate.append(DebateItem(raised_by=report.role, issue=issue))
                if report.stance != 'support':
                    debate.append(DebateItem(raised_by=report.role, issue=f'{report.stance}: {report.rationale}'))
                if not report.findings:
                    debate.append(DebateItem(raised_by=report.role, issue='No supporting evidence supplied'))
            # Seventh invocation belongs to the same sixth agent: final adjudication.
            try:
                self.budget.reserve()
                decision_agent = next(a for a in self.agents if a.role == AgentRole.FINAL_DECISION)
                if not decision_agent.adjudicate(tuple(reports), tuple(debate)):
                    failures.append('decision_agent_rejected')
            except Exception:
                failures.append('final_decision_failure_or_budget_exhausted')
            if debate: failures.append('unresolved_debate')
        elif not failures:
            failures.append('incomplete_team')
        return TeamResult(candidate_id=snapshot.candidate_id, snapshot_id=digest, decided_at=now,
            reports=tuple(reports), debate=tuple(debate), verdict='NO_ACTION' if failures else 'PAPER_PLAN',
            failures=tuple(dict.fromkeys(failures)), plan=None if failures else plan,
            calls_used=self.budget.used-initial_calls)
