from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock
import pytest
from market_radar_ai.market_data.http import ReadOnlyJsonClient
from market_radar_ai.market_data.providers.catalogues import Trading212Catalogue, KrakenCatalogue
from market_radar_ai.market_data.providers.fx import YahooFxProvider
from market_radar_ai.market_data.providers.coingecko import CoinGeckoProvider
from market_radar_ai.market_data.batch import fetch_batch
from market_radar_ai.market_data.models import Candle, ProviderResult


def response(code=200, payload=None, headers=None):
    return Mock(status_code=code, headers=headers or {}, json=Mock(return_value=payload))


def client(responses, **kwargs):
    session = Mock()
    session.get.side_effect = responses
    c = ReadOnlyJsonClient(session=session, sleeper=Mock(), min_interval=0, **kwargs)
    return c, session


def test_retry_then_cache_and_defensive_copy():
    c, s = client([response(503), response(payload={'a': [1]})])
    result = c.get_json('https://example.test')
    result['a'].append(2)
    assert c.get_json('https://example.test') == {'a': [1]}
    assert s.get.call_count == 2 and c.metrics()['retries'] == 1


def test_auth_failure_not_retried_or_logged():
    c, s = client([response(401)])
    with pytest.raises(RuntimeError, match='provider_response_invalid'):
        c.get_json('https://example.test')
    assert s.get.call_count == 1


def test_long_retry_after_defers_instead_of_hammering():
    c, s = client([response(429, headers={'Retry-After': '120'})])
    with pytest.raises(RuntimeError, match='backoff_exceeds_budget'):
        c.get_json('https://example.test')
    assert s.get.call_count == 1


def test_request_budget_is_hard_limit():
    c, s = client([response(503)], max_requests=1)
    with pytest.raises(RuntimeError, match='request_budget_exhausted'):
        c.get_json('https://example.test')
    assert s.get.call_count == 1


def test_cache_expiry_does_not_serve_stale_on_error():
    clock = Mock(side_effect=[0, 0, 100, 100, 100])
    c, _ = client([response(payload={'a': 1}), response(401)], clock=clock, cache_ttl=10)
    c.get_json('https://example.test')
    with pytest.raises(RuntimeError):
        c.get_json('https://example.test')


def test_t212_missing_credentials_makes_no_request(monkeypatch):
    monkeypatch.delenv('TRADING212_API_KEY', raising=False)
    monkeypatch.delenv('TRADING212_API_SECRET', raising=False)
    with pytest.raises(RuntimeError, match='credentials_missing'):
        Trading212Catalogue().fetch()


def test_t212_preserves_isin_and_broker_identity():
    c = Mock()
    c.get_json.return_value = [dict(ticker='ABC_US_EQ', isin='US0000000001', currencyCode='USD', type='STOCK', name='ABC', workingScheduleId=1)]
    row = Trading212Catalogue(c).fetch()[0]
    assert row.isin == 'US0000000001' and row.ticker == 'ABC_US_EQ'
    c.get_json.assert_called_once_with(Trading212Catalogue.URL)


def test_kraken_catalogue_only_online_eur():
    c = Mock()
    c.get_json.return_value = {'error': [], 'result': {
        'XXBTZEUR': dict(quote='ZEUR', status='online', altname='XBTEUR', wsname='XBT/EUR'),
        'BAD': dict(quote='ZUSD', status='online'), 'OFF': dict(quote='ZEUR', status='cancel_only')}}
    result = KrakenCatalogue(c).discover_eur()
    assert [i.symbol for i in result.instruments] == ['XBTEUR']
    assert result.instruments[0].provider_symbol == 'XXBTZEUR'


def test_fx_direction_and_source_timestamp():
    now = datetime.now(timezone.utc)
    stamp = now-timedelta(minutes=5)
    candle = Candle(symbol='EURUSD=X', interval='5m', timestamp=stamp, open='1.25', high='1.25', low='1.25', close='1.25', volume=0, quote_currency='USD', source='yahoo_finance')
    provider = Mock()
    provider.fetch_history.return_value = ProviderResult(provider='yahoo_finance', retrieved_at=now, candles=[candle])
    result = YahooFxProvider(provider).fetch('USD', now=now)
    assert result.eur_per_unit == Decimal('0.8') and result.observed_at == stamp
    with pytest.raises(RuntimeError, match='freshness'):
        YahooFxProvider(provider).fetch('USD', now=now+timedelta(hours=1))


def test_batch_failure_isolation_and_deferral():
    def fetch(symbol):
        if symbol == 'BAD': raise RuntimeError('secret error details')
        return ProviderResult(provider='test', retrieved_at=datetime.now(timezone.utc))
    result = fetch_batch(['BAD', 'OK', 'OK', 'LATER'], fetch, max_symbols=2)
    assert result.results['BAD'].status == 'error' and result.results['OK'].status == 'ok'
    assert result.deferred == ['LATER'] and result.duplicate_count == 1
    assert 'secret' not in result.results['BAD'].model_dump_json()


def test_paginated_discovery_and_partial_failure():
    provider = CoinGeckoProvider()
    provider.client = Mock()
    rows = [dict(id=f'coin{i}', symbol=f'C{i}') for i in range(250)]
    provider.client.get_json.side_effect = [rows, RuntimeError('rate limit')]
    result = provider.discover_eur_markets(500)
    assert result.status == 'partial' and len(result.instruments) == 250
    assert provider.client.get_json.call_args.kwargs['params']['page'] == 2


def test_robinhood_scopes_list_to_supported_heading():
    from market_radar_ai.market_data.providers.robinhood import parse_supported_crypto
    html = '<ul><li>Wrong (BAD)</li></ul><h2>Supported crypto</h2><ul><li><a>Bitcoin (BTC)</a></li><li>Ethereum (ETH)</li></ul><h2>Support</h2><ul><li>Footer (BAD)</li></ul>'
    assert [r['symbol'] for r in parse_supported_crypto(html)] == ['BTC', 'ETH']
    with pytest.raises(ValueError):
        parse_supported_crypto('<h2>Supported crypto</h2><li>Changed format</li>')


def test_batch_time_budget_defers_remaining():
    ticks = iter([0, 0, 5])
    result = fetch_batch(['ONE', 'TWO'], lambda s: ProviderResult(provider='test', retrieved_at=datetime.now(timezone.utc)), max_seconds=4, clock=lambda: next(ticks))
    assert list(result.results) == ['ONE'] and result.deferred == ['TWO']
