from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import requests
from ..http import ReadOnlyJsonClient
from ..models import Candle, ProviderResult, ValidationIssue

class KrakenProvider:
    """Public Kraken OHLC endpoint. The API caps recent history at 720 candles."""
    BASE_URL = "https://api.kraken.com/0/public"
    def __init__(self, session: requests.Session | None = None, timeout: int = 15):
        self.client = ReadOnlyJsonClient(session=session, timeout=timeout)
    def fetch_ohlc(self, pair: str, interval_minutes: int = 5) -> ProviderResult:
        retrieved = datetime.now(timezone.utc)
        try:
            payload = self.client.get_json(f"{self.BASE_URL}/OHLC", params={"pair": pair, "interval": interval_minutes})
            if payload.get("error"): raise RuntimeError("; ".join(payload["error"]))
            result = payload.get("result", {})
            pair_key = next((key for key in result if key != "last"), None)
            if pair_key is None: raise RuntimeError("Kraken response contained no OHLC pair data")
            candles = []
            # Kraken documents the final row as the current, not-yet-committed interval.
            # Exclude it so downstream analysis only sees completed candles.
            for row in result[pair_key][:-1]:
                candles.append(Candle(symbol=pair.upper(), interval=f"{interval_minutes}m",
                    timestamp=datetime.fromtimestamp(int(row[0]), tz=timezone.utc),
                    open=Decimal(str(row[1])), high=Decimal(str(row[2])), low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])), volume=Decimal(str(row[6])),
                    quote_currency="EUR" if pair.upper().endswith("EUR") else "UNKNOWN", source="kraken"))
            if not candles:
                raise ValueError("No completed candles returned")
            return ProviderResult(provider="kraken", retrieved_at=retrieved, candles=candles)
        except Exception as exc:
            return ProviderResult(provider="kraken", retrieved_at=retrieved, status="error",
                issues=[ValidationIssue(code="provider_error", message=str(exc), symbol=pair)])
