"""Conservative research admission. Evidence must be supplied by verified adapters.

This module does not infer broker availability from an exchange listing and does
not emit trade recommendations. FX rates are EUR per one native currency unit.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from .models import Instrument, ProviderResult
from .quality import validate_candles


class EligibilityEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    broker: Literal['trading212_invest', 'robinhood_europe']
    asset_class: Literal['equity', 'crypto']
    provider_symbol: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    broker_instrument_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    verified_at: AwareDatetime
    expires_at: AwareDatetime
    eligible: bool

    @model_validator(mode='after')
    def valid_window(self):
        if self.expires_at <= self.verified_at:
            raise ValueError('Eligibility expiry must follow verification')
        return self


class FxQuote(BaseModel):
    model_config = ConfigDict(frozen=True)
    native_currency: str = Field(min_length=3, max_length=3)
    eur_per_unit: Decimal = Field(gt=0, allow_inf_nan=False)
    observed_at: AwareDatetime
    source: str = Field(min_length=1)


class Admission(BaseModel):
    model_config = ConfigDict(frozen=True)
    accepted: bool
    failures: tuple[str, ...]
    native_close: Decimal | None = None
    eur_close: Decimal | None = None
    fx_source: str | None = None
    fx_observed_at: AwareDatetime | None = None


def admit_research(instrument: Instrument, data: ProviderResult, *,
                   evidence: EligibilityEvidence | None, fx: FxQuote | None,
                   now: datetime, interval_seconds: int = 300,
                   max_age_seconds: int = 600, max_fx_age_seconds: int = 900,
                   min_candles: int = 20) -> Admission:
    """Reject unknown identity, eligibility, incomplete data or stale FX.

    Intended for a single intraday series during an active session. Exchange
    calendar handling remains outside this gate; closed sessions fail freshness.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be timezone-aware')
    if min(interval_seconds, max_age_seconds, max_fx_age_seconds, min_candles) <= 0:
        raise ValueError('Admission limits must be positive')
    failures = []
    if not instrument.active:
        failures.append('inactive_instrument')
    expected_broker = 'trading212_invest' if instrument.asset_class == 'equity' else 'robinhood_europe'
    if not instrument.provider_symbol:
        failures.append('missing_provider_identity')
    if evidence is None:
        failures.append('broker_unverified')
    elif (not evidence.eligible or evidence.broker != expected_broker
          or evidence.asset_class != instrument.asset_class
          or evidence.provider_symbol != instrument.provider_symbol
          or evidence.venue != instrument.venue
          or not evidence.verified_at <= now < evidence.expires_at):
        failures.append('broker_evidence_invalid')
    if data.status != 'ok' or data.issues:
        failures.append('provider_not_clean')
    rows = data.candles
    if len(rows) < min_candles:
        failures.append('insufficient_history')
    if any(c.symbol != instrument.symbol or c.quote_currency != instrument.quote_currency
           for c in rows):
        failures.append('candle_identity_mismatch')
    if len({(c.interval, c.source) for c in rows}) > 1:
        failures.append('mixed_series')
    expected_interval = f'{interval_seconds // 60}m'
    if interval_seconds % 60 or any(c.interval != expected_interval for c in rows):
        failures.append('interval_mismatch')
    if any(c.timestamp + timedelta(seconds=interval_seconds) > now for c in rows):
        failures.append('incomplete_candle')
    failures.extend(i.code for i in validate_candles(
        rows, now=now, max_age_seconds=max_age_seconds,
        expected_interval_seconds=interval_seconds))
    rate = Decimal(1)
    fx_source, fx_time = 'native_eur', now
    if instrument.quote_currency != 'EUR':
        if (fx is None or fx.native_currency != instrument.quote_currency
                or not 0 <= (now - fx.observed_at).total_seconds() <= max_fx_age_seconds):
            failures.append('fx_unavailable_or_stale')
        else:
            rate, fx_source, fx_time = fx.eur_per_unit, fx.source, fx.observed_at
    if failures:
        return Admission(accepted=False, failures=tuple(dict.fromkeys(failures)))
    latest = max(rows, key=lambda c: c.timestamp)
    return Admission(accepted=True, failures=(), native_close=latest.close,
                     eur_close=latest.close * rate, fx_source=fx_source, fx_observed_at=fx_time)
