from __future__ import annotations
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from ..models import Candle, ProviderResult, ValidationIssue

class YahooFinanceProvider:
    """Yahoo Finance chart adapter via optional yfinance; not a broker execution feed."""
    def fetch_history(self, symbol: str, *, period: str = "5d", interval: str = "5m", auto_adjust: bool = False) -> ProviderResult:
        retrieved = datetime.now(timezone.utc)
        try:
            intervals = {"1m": 60, "2m": 120, "5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "90m": 5400, "1h": 3600}
            if interval not in intervals:
                raise ValueError("Only supported intraday intervals are allowed")
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            frame = ticker.history(period=period, interval=interval, auto_adjust=auto_adjust, prepost=False)
            if frame.empty: raise RuntimeError("Yahoo Finance returned no candles")
            currency = ticker.fast_info.get("currency")
            if not currency:
                raise ValueError("Quote currency unavailable; refusing to assume USD")
            candles = []
            for stamp, row in frame.iterrows():
                ts = stamp.to_pydatetime()
                if ts.tzinfo is None:
                    raise ValueError("Provider returned timezone-naive candle")
                if ts + timedelta(seconds=intervals[interval]) > retrieved:
                    continue
                candles.append(Candle(symbol=symbol.upper(), interval=interval, timestamp=ts,
                    open=Decimal(str(row["Open"])), high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])), close=Decimal(str(row["Close"])),
                    volume=Decimal(str(row["Volume"])), quote_currency=currency, source="yahoo_finance"))
            if not candles:
                raise ValueError("No completed candles returned")
            return ProviderResult(provider="yahoo_finance", retrieved_at=retrieved, candles=candles)
        except Exception as exc:
            return ProviderResult(provider="yahoo_finance", retrieved_at=retrieved, status="error",
                issues=[ValidationIssue(code="provider_error", message=str(exc), symbol=symbol)])
