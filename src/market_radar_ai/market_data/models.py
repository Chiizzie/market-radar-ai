from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str | None = None
    asset_class: Literal["equity", "crypto"]
    quote_currency: str
    venue: str
    provider_symbol: str | None = None
    market_cap_eur: Decimal | None = None
    average_volume_eur: Decimal | None = None
    active: bool = True

class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    interval: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_currency: str
    source: str

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Candle timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_ohlc(self):
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("High is below another OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Low is above another OHLC value")
        return self

class ValidationIssue(BaseModel):
    code: str
    message: str
    symbol: str | None = None
    timestamp: datetime | None = None

class ProviderResult(BaseModel):
    provider: str
    retrieved_at: datetime
    instruments: list[Instrument] = Field(default_factory=list)
    candles: list[Candle] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    status: Literal["ok", "partial", "error"] = "ok"
