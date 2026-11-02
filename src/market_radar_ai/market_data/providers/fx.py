"""Indicative Yahoo FX; never substitutes daily reference rates for intraday data."""
from datetime import datetime, timezone
from decimal import Decimal
from ..admission import FxQuote
from .yahoo import YahooFinanceProvider


class YahooFxProvider:
    # Explicit pair direction: USD/GBP/CHF/JPY units per EUR, inverted below.
    PAIRS = {'USD': 'EURUSD=X', 'GBP': 'EURGBP=X', 'CHF': 'EURCHF=X', 'JPY': 'EURJPY=X'}

    def __init__(self, provider=None):
        self.provider = provider or YahooFinanceProvider()

    def fetch(self, currency, *, now=None, max_age_seconds=900):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or max_age_seconds <= 0:
            raise ValueError('Invalid FX clock or freshness limit')
        if currency not in self.PAIRS:
            raise ValueError('unsupported_fx_currency')
        symbol = self.PAIRS[currency]
        result = self.provider.fetch_history(symbol, period='1d', interval='5m')
        if result.status != 'ok' or result.issues or not result.candles:
            raise RuntimeError('fx_provider_unavailable')
        latest = max(result.candles, key=lambda c: c.timestamp)
        if (latest.symbol != symbol or latest.quote_currency != currency
                or not 300 <= (now-latest.timestamp).total_seconds() <= max_age_seconds):
            raise RuntimeError('fx_identity_or_freshness_failed')
        return FxQuote(native_currency=currency, eur_per_unit=Decimal(1)/latest.close,
                       observed_at=latest.timestamp, source=f'yahoo_finance:{symbol}:5m')
