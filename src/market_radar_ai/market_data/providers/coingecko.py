from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import requests
from ..models import Instrument, ProviderResult, ValidationIssue

class CoinGeckoProvider:
    """Public CoinGecko market discovery; market-cap rank is not a trade signal."""
    BASE_URL = "https://api.coingecko.com/api/v3"
    def __init__(self, session: requests.Session | None = None, timeout: int = 15):
        self.session, self.timeout = session or requests.Session(), timeout
    def discover_eur_markets(self, limit: int = 250) -> ProviderResult:
        retrieved = datetime.now(timezone.utc)
        try:
            response = self.session.get(f"{self.BASE_URL}/coins/markets", params={
                "vs_currency": "eur", "order": "market_cap_desc",
                "per_page": min(max(limit, 1), 250), "page": 1, "sparkline": "false"}, timeout=self.timeout)
            response.raise_for_status()
            instruments = []
            for item in response.json():
                symbol = str(item.get("symbol", "")).upper()
                if not symbol: continue
                instruments.append(Instrument(symbol=f"{symbol}/EUR", name=item.get("name"),
                    asset_class="crypto", quote_currency="EUR", venue="CoinGecko discovery",
                    provider_symbol=item.get("id"),
                    market_cap_eur=Decimal(str(item["market_cap"])) if item.get("market_cap") is not None else None,
                    average_volume_eur=Decimal(str(item["total_volume"])) if item.get("total_volume") is not None else None))
            return ProviderResult(provider="coingecko", retrieved_at=retrieved, instruments=instruments)
        except Exception as exc:
            return ProviderResult(provider="coingecko", retrieved_at=retrieved, status="error",
                issues=[ValidationIssue(code="provider_error", message=str(exc))])
