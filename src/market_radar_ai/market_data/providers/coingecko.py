from datetime import datetime, timezone
from decimal import Decimal
from ..http import ReadOnlyJsonClient
from ..models import Instrument, ProviderResult, ValidationIssue


class CoinGeckoProvider:
    """Bounded paginated discovery; provider IDs are retained, not ticker-matched."""
    BASE_URL = 'https://api.coingecko.com/api/v3'

    def __init__(self, session=None, timeout=15):
        self.client = ReadOnlyJsonClient(session=session, timeout=timeout,
                                        min_interval=2, cache_ttl=60, max_requests=30)

    def discover_eur_markets(self, limit=250):
        if not 1 <= limit <= 2500:
            raise ValueError('Discovery limit must be between 1 and 2500')
        now = datetime.now(timezone.utc)
        instruments, seen = [], set()
        try:
            page_size = min(limit, 250)
            for page in range(1, (limit + page_size - 1) // page_size + 1):
                payload = self.client.get_json(f'{self.BASE_URL}/coins/markets', params={
                    'vs_currency': 'eur', 'order': 'market_cap_desc', 'per_page': page_size,
                    'page': page, 'sparkline': 'false'})
                if not isinstance(payload, list):
                    raise ValueError('Malformed discovery response')
                if not payload:
                    break
                for item in payload:
                    identity, symbol = item['id'], str(item['symbol']).upper()
                    if not identity or not symbol:
                        raise ValueError('Missing discovery identity')
                    if identity in seen:
                        continue
                    seen.add(identity)
                    instruments.append(Instrument(symbol=f'{symbol}/EUR', name=item.get('name'),
                        asset_class='crypto', quote_currency='EUR', venue='CoinGecko discovery',
                        provider_symbol=identity,
                        market_cap_eur=Decimal(str(item['market_cap'])) if item.get('market_cap') is not None else None,
                        average_volume_eur=Decimal(str(item['total_volume'])) if item.get('total_volume') is not None else None))
                if len(payload) < page_size:
                    break
            if not instruments:
                raise ValueError('Empty discovery result')
            return ProviderResult(provider='coingecko', retrieved_at=now, instruments=instruments[:limit])
        except (RuntimeError, ValueError, KeyError, TypeError):
            return ProviderResult(provider='coingecko', retrieved_at=now, instruments=instruments[:limit],
                status='partial' if instruments else 'error', issues=[ValidationIssue(
                    code='discovery_incomplete', message='Discovery request failed or response was invalid')])
