from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import sys
import pandas as pd
from market_radar_ai.market_data.providers import KrakenProvider, CoinGeckoProvider, YahooFinanceProvider


def session(payload):
    client = Mock()
    client.get.return_value.json.return_value = payload
    client.get.return_value.status_code = 200
    return client


def test_kraken_excludes_forming_candle():
    rows = [[1000, '10', '12', '9', '11', '10', '2', 1],
            [1300, '10', '12', '9', '11', '10', '2', 1]]
    result = KrakenProvider(session({'error': [], 'result': {'XXBTZEUR': rows, 'last': 1300}})).fetch_ohlc('XBTEUR')
    assert result.status == 'ok' and len(result.candles) == 1
    assert result.candles[0].timestamp.timestamp() == 1000


def test_kraken_api_error_fails_closed():
    result = KrakenProvider(session({'error': ['EQuery:Unknown asset pair']})).fetch_ohlc('BAD')
    assert result.status == 'error' and not result.candles


def test_coingecko_preserves_identity_and_eur_request():
    client = session([{'id': 'bitcoin', 'symbol': 'btc', 'name': 'Bitcoin', 'market_cap': 100, 'total_volume': 20}])
    result = CoinGeckoProvider(client).discover_eur_markets()
    assert result.instruments[0].provider_symbol == 'bitcoin'
    assert client.get.call_args.kwargs['params']['vs_currency'] == 'eur'


def yahoo(monkeypatch, currency='EUR', naive=False):
    now = datetime.now(timezone.utc)
    index = pd.DatetimeIndex([now-timedelta(minutes=10), now])
    if naive:
        index = index.tz_localize(None)
    frame = pd.DataFrame({'Open': [10, 10], 'High': [12, 12], 'Low': [9, 9], 'Close': [11, 11], 'Volume': [2, 2]}, index=index)
    ticker = Mock()
    ticker.history.return_value = frame
    ticker.fast_info = {'currency': currency}
    monkeypatch.setitem(sys.modules, 'yfinance', Mock(Ticker=Mock(return_value=ticker)))
    return YahooFinanceProvider().fetch_history('TEST')


def test_yahoo_preserves_currency_and_excludes_open_bar(monkeypatch):
    result = yahoo(monkeypatch)
    assert result.status == 'ok' and len(result.candles) == 1
    assert result.candles[0].quote_currency == 'EUR'


def test_yahoo_missing_currency_fails_closed(monkeypatch):
    result = yahoo(monkeypatch, currency=None)
    assert result.status == 'error' and not result.candles


def test_yahoo_naive_timestamp_fails_closed(monkeypatch):
    result = yahoo(monkeypatch, naive=True)
    assert result.status == 'error' and not result.candles
