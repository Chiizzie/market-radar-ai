from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from ..models import Candle, ProviderResult, ValidationIssue

class YahooFinanceProvider:
    """Yahoo Finance chart adapter via optional yfinance; not a broker execution feed."""
    def fetch_history(self, symbol: str, *, period: str = "5d", interval: str = "5m", auto_adjust: bool = False) -> ProviderResult:
        retrieved = datetime.now(timezone.utc)
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            frame = ticker.history(period=period, interval=interval, auto_adjust=auto_adjust, prepost=False)
            if frame.empty: raise RuntimeError("Yahoo Finance returned no candles")
            try: currency = ticker.fast_info.get("currency") or "USD"
            except Exception: currency = "USD"
            candles = []
            for stamp, row in frame.iterrows():
                ts = stamp.to_pydatetime()
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                candles.append(Candle(symbol=symbol.upper(), interval=interval, timestamp=ts,
                    open=Decimal(str(row["Open"])), high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])), close=Decimal(str(row["Close"])),
                    volume=Decimal(str(row["Volume"])), quote_currency=currency, source="yahoo_finance"))
            return ProviderResult(provider="yahoo_finance", retrieved_at=retrieved, candles=candles)
        except Exception as exc:
            return ProviderResult(provider="yahoo_finance", retrieved_at=retrieved, status="error",
                issues=[ValidationIssue(code="provider_error", message=str(exc), symbol=symbol)])
