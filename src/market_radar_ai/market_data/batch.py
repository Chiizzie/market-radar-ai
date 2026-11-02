"""Bounded sequential candle retrieval with explicit deferral and health counts."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from .models import ProviderResult, ValidationIssue


@dataclass
class BatchResult:
    results: dict[str, ProviderResult] = field(default_factory=dict)
    deferred: list[str] = field(default_factory=list)
    duplicate_count: int = 0


def fetch_batch(symbols, fetch, *, max_symbols=20, max_seconds=120, clock=monotonic):
    if max_symbols < 1 or max_seconds <= 0:
        raise ValueError('Batch budgets must be positive')
    output = BatchResult()
    unique = list(dict.fromkeys(symbols))
    output.duplicate_count = len(symbols) - len(unique)
    start = clock()
    for index, symbol in enumerate(unique):
        if index >= max_symbols or clock() - start >= max_seconds:
            output.deferred.extend(unique[index:])
            break
        try:
            result = fetch(symbol)
            if not isinstance(result, ProviderResult):
                raise ValueError('invalid_provider_result')
            output.results[symbol] = result
        except Exception:
            output.results[symbol] = ProviderResult(provider='batch', retrieved_at=datetime.now(timezone.utc),
                status='error', issues=[ValidationIssue(code='fetch_failed', message='Provider call failed', symbol=symbol)])
    return output
