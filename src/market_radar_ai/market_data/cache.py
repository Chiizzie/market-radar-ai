"""Bounded candle cache; a cache hit never refreshes the source timestamp."""
from collections import OrderedDict
from datetime import datetime
from .models import ProviderResult
from .quality import validate_candles


class CandleCache:
    def __init__(self, capacity=500, ttl_seconds=30, max_candle_age_seconds=900):
        if capacity < 1 or ttl_seconds <= 0 or max_candle_age_seconds <= 0:
            raise ValueError('Positive cache limits required')
        self.capacity = capacity
        self.ttl = ttl_seconds
        self.max_age = max_candle_age_seconds
        self.entries = OrderedDict()

    def _usable(self, result, now):
        if now.tzinfo is None or result.retrieved_at.tzinfo is None:
            raise ValueError('Aware timestamps required')
        age = (now - result.retrieved_at).total_seconds()
        return (0 <= age < self.ttl and result.status == 'ok' and not result.issues
                and bool(result.candles)
                and not validate_candles(result.candles, now=now, max_age_seconds=self.max_age)
                and all(c.interval == '5m' and (now-c.timestamp).total_seconds() >= 300
                        for c in result.candles))

    def put(self, provider, symbol, result: ProviderResult, *, now: datetime):
        key = (provider, symbol.upper(), '5m')
        self.entries.pop(key, None)
        if (result.provider != provider or any(c.symbol.upper() != symbol.upper()
                or c.source != provider for c in result.candles) or not self._usable(result, now)):
            return False
        self.entries[key] = result.model_copy(deep=True)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return True

    def get(self, provider, symbol, *, now: datetime):
        key = (provider, symbol.upper(), '5m')
        result = self.entries.get(key)
        if result is None:
            return None
        if not self._usable(result, now):
            del self.entries[key]
            return None
        self.entries.move_to_end(key)
        return result.model_copy(deep=True)
