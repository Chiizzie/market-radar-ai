from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterable
from .models import Candle, ValidationIssue

def validate_candles(candles: Iterable[Candle], *, now: datetime | None = None,
                     max_age_seconds: int | None = None,
                     expected_interval_seconds: int | None = None) -> list[ValidationIssue]:
    """Report quality issues without silently repairing or dropping source data."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    rows = sorted(candles, key=lambda c: (c.symbol, c.timestamp))
    issues: list[ValidationIssue] = []
    if not rows:
        return [ValidationIssue(code="empty_candles", message="No completed candles available")]
    latest = {}
    for row in rows:
        latest[(row.symbol, row.interval, row.source)] = row.timestamp
    seen: set[tuple[str, str, str, datetime]] = set()
    for candle in rows:
        key = (candle.symbol, candle.interval, candle.source, candle.timestamp)
        if key in seen:
            issues.append(ValidationIssue(code="duplicate_candle", message="Duplicate symbol/timestamp candle", symbol=candle.symbol, timestamp=candle.timestamp))
        seen.add(key)
        age = (now.astimezone(timezone.utc) - candle.timestamp).total_seconds()
        if age < -60:
            issues.append(ValidationIssue(code="future_candle", message="Candle timestamp is more than 60 seconds in the future", symbol=candle.symbol, timestamp=candle.timestamp))
        if (max_age_seconds is not None and age > max_age_seconds
                and candle.timestamp == latest[(candle.symbol, candle.interval, candle.source)]):
            issues.append(ValidationIssue(code="stale_candle", message=f"Candle is older than {max_age_seconds} seconds", symbol=candle.symbol, timestamp=candle.timestamp))
    if expected_interval_seconds:
        grouped: dict[tuple[str, str, str], list[Candle]] = {}
        for candle in rows:
            grouped.setdefault((candle.symbol, candle.interval, candle.source), []).append(candle)
        for (symbol, _, _), series in grouped.items():
            for prev, current in zip(series, series[1:]):
                gap = (current.timestamp - prev.timestamp).total_seconds()
                if gap > expected_interval_seconds * 1.5:
                    issues.append(ValidationIssue(code="candle_gap", message=f"Gap of {int(gap)} seconds between candles", symbol=symbol, timestamp=current.timestamp))
    return issues
