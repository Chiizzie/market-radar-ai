"""Allowlisted free research diagnostics; no trade admission or private ledger data."""
from typing import Literal
from pydantic import AwareDatetime, Field
from ..agents.paper_team import Frozen
from ..agents.paper_outcomes import PaperOutcome
from ..agents.early_screening import screen


class TrackedRow(Frozen):
    packet_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    symbol: str = Field(min_length=1,max_length=100)
    state: Literal['watching','open_simulation','closed','not_filled','unresolved']
    quote_count: int = Field(ge=0)
    outcome: PaperOutcome


class TrackingReport(Frozen):
    schema_version: Literal['paper-tracking-v1']
    as_of: AwareDatetime
    trades: list[TrackedRow] = Field(max_length=1000)
    model_calls: Literal[0]
    trade_authorized: Literal[False]
    note: str = Field(min_length=1,max_length=1000)


def build_diagnostics(document, *, now):
    tracking=None
    if document.get('paper_tracking_report') is not None:
        report=TrackingReport.model_validate(document['paper_tracking_report'])
        if not 0 <= (now-report.as_of).total_seconds() <= 300:
            raise ValueError('paper_tracking_report_clock_mismatch')
        tracking=report.model_dump(mode='json')
    return {'schema_version':'research-diagnostics-v1','early_screening':screen(document,now=now),
            'paper_tracking':tracking,'trade_authorized':False}
