"""Read-only catalogues. Listings are discovery, never automatic broker evidence."""
from datetime import datetime, timezone
import os
import requests
from pydantic import BaseModel, Field
from ..http import ReadOnlyJsonClient
from ..models import Instrument, ProviderResult, ValidationIssue


class BrokerInstrument(BaseModel):
    ticker: str = Field(min_length=1)
    isin: str = Field(min_length=1)
    currencyCode: str = Field(min_length=3, max_length=3)
    type: str
    name: str
    workingScheduleId: int


class Trading212Catalogue:
    URL = 'https://live.trading212.com/api/v0/equity/metadata/instruments'

    def __init__(self, client=None):
        self.client = client

    def fetch(self):
        client = self.client
        if client is None:
            key, secret = os.getenv('TRADING212_API_KEY'), os.getenv('TRADING212_API_SECRET')
            if not key or not secret:
                raise RuntimeError('trading212_credentials_missing')
            session = requests.Session()
            session.auth = (key, secret)
            client = self.client = ReadOnlyJsonClient(session=session, min_interval=50,
                                                      cache_ttl=600, max_requests=3)
        payload = client.get_json(self.URL)
        if not isinstance(payload, list) or not payload:
            raise ValueError('invalid_broker_catalogue')
        rows = [BrokerInstrument.model_validate(row) for row in payload if row.get('type') in ('STOCK', 'ETF')]
        if len({r.ticker for r in rows}) != len(rows):
            raise ValueError('duplicate_broker_identity')
        return rows


class KrakenCatalogue:
    URL = 'https://api.kraken.com/0/public/AssetPairs'

    def __init__(self, client=None):
        self.client = client or ReadOnlyJsonClient(cache_ttl=3600)

    def discover_eur(self):
        now = datetime.now(timezone.utc)
        try:
            payload = self.client.get_json(self.URL)
            if payload.get('error'):
                raise ValueError('kraken_catalogue_error')
            instruments = []
            for key, row in payload['result'].items():
                if row.get('quote') != 'ZEUR' or row.get('status') != 'online':
                    continue
                alias = row['altname']
                instruments.append(Instrument(symbol=alias, provider_symbol=key,
                    name=row.get('wsname'), asset_class='crypto', quote_currency='EUR', venue='Kraken'))
            if not instruments:
                raise ValueError('empty_eur_catalogue')
            return ProviderResult(provider='kraken_catalogue', retrieved_at=now, instruments=instruments)
        except (RuntimeError, ValueError, KeyError, TypeError):
            return ProviderResult(provider='kraken_catalogue', retrieved_at=now, status='error',
                issues=[ValidationIssue(code='catalogue_error', message='Kraken catalogue unavailable or malformed')])
