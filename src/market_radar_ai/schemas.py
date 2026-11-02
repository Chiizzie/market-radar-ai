from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field, ConfigDict

class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"

class FinalVerdict(StrEnum):
    ACTIONABLE_NOW = "ACTIONABLE_NOW"
    WATCH_FOR_ENTRY = "WATCH_FOR_ENTRY"
    NO_ACTION = "NO_ACTION"

class CandidateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate_id: str
    symbol: str
    asset_class: str
    exchange: str | None = None
    observed_at: datetime
    currency: str
    last_price: float = Field(gt=0)
    source_ids: list[str]
    data_quality_passed: bool
    data_quality_notes: list[str] = []

class Evidence(BaseModel):
    claim: str
    source: str
    observed_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)

class AgentReport(BaseModel):
    candidate_id: str
    agent_id: str
    model_id: str
    prompt_version: str
    generated_at: datetime
    data_snapshot_id: str
    direction: Direction
    verdict: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = []
    risks: list[str] = []
    missing_data: list[str] = []
    rationale: str

class TradePlan(BaseModel):
    direction: Direction
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    target_1: float = Field(gt=0)
    target_2: float | None = Field(default=None, gt=0)
    quantity: float = Field(gt=0)
    planned_loss_eur: float = Field(ge=0)
    risk_reward: float = Field(gt=0)
    invalidation: str
    timeframe: str
    broker: str

class FinalDecision(BaseModel):
    candidate_id: str
    verdict: FinalVerdict
    decided_at: datetime
    rationale: str
    unresolved_objections: list[str] = []
    hard_gate_failures: list[str] = []
    trade_plan: TradePlan | None = None
