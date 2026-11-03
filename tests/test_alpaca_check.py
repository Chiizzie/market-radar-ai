from datetime import datetime, timezone, timedelta
import json
import pytest
from market_radar_ai.market_data.alpaca_check import AlpacaReader, DataError, capture

NOW = datetime(2026, 11, 3, 16, 30, tzinfo=timezone.utc)

class Reader:
    def __init__(self, mutate=None):
        self.mutate = mutate
    def get(self, kind, params):
        data = {
            'quote': {'quote': {'t': (NOW-timedelta(seconds=10)).isoformat(), 'bp': 200, 'ap': 200.05}},
            'bars': {'bars': [{'t': (NOW-timedelta(minutes=120-5*i)).isoformat(), 'o': 200, 'h': 202, 'l': 199, 'c': 201, 'v': 100} for i in range(24)]},
            'news': {'news': [{'id': 1, 'headline': 'Example', 'symbols': ['NVDA'], 'created_at': (NOW-timedelta(hours=1)).isoformat()}]}
        }[kind]
        if self.mutate:
            self.mutate(kind, data)
        return data

def test_fresh_data_does_not_authorize_trade():
    result = capture(Reader(), NOW)
    assert result['state'] == 'data_received'
    assert result['quote']['status'] == 'fresh'
    assert result['bars']['count'] == 24
    assert result['bars']['minimum_20_bars_met']
    assert result['bars']['gap_count'] == 0
    assert result['news']['count'] == 1
    assert not result['trade_authorized'] and result['model_calls'] == 0
    assert 'not consolidated' in result['coverage']

@pytest.mark.parametrize('fault', ['future', 'nan', 'duplicate', 'pagination'])
def test_invalid_bars_fail_independently(fault):
    def mutate(kind, data):
        if kind != 'bars': return
        if fault == 'future': data['bars'][-1]['t'] = (NOW+timedelta(minutes=1)).isoformat()
        if fault == 'nan': data['bars'][0]['c'] = 'NaN'
        if fault == 'duplicate': data['bars'].append(data['bars'][-1])
        if fault == 'pagination': data['next_page_token'] = 'more'
    result = capture(Reader(mutate), NOW)
    assert result['bars']['status'] == 'error'
    assert result['quote']['status'] == 'fresh'
    assert result['state'] == 'partial_or_blocked'

def test_stale_quote_and_unfinished_bar():
    def mutate(kind, data):
        if kind == 'quote': data['quote']['t'] = (NOW-timedelta(minutes=10)).isoformat()
        if kind == 'bars':
            bar = dict(data['bars'][-1], t=(NOW-timedelta(minutes=1)).isoformat())
            data['bars'].append(bar)
    result = capture(Reader(mutate), NOW)
    assert result['quote']['status'] == 'stale'
    assert result['bars']['count'] == 24
    assert result['bars']['unfinished_bars_excluded'] == 1

@pytest.mark.parametrize('status', [200, 401, 403, 429, 302])
def test_transport_is_read_only_and_sanitized(monkeypatch, status):
    monkeypatch.setenv('ALPACA_API_KEY', 'private-key')
    monkeypatch.setenv('ALPACA_API_SECRET', 'private-secret')
    class Response:
        status_code = status
        def json(self): raise ValueError('private-secret')
    class Session:
        def get(self, url, **kwargs):
            assert url == 'https://data.alpaca.markets/v2/stocks/NVDA/quotes/latest'
            assert kwargs['allow_redirects'] is False
            assert kwargs['timeout'] == 15
            return Response()
    with pytest.raises(DataError) as exc:
        AlpacaReader(Session()).get('quote', {'feed': 'iex'})
    assert 'private' not in str(exc.value)
    assert str(exc.value) == ('transport_or_json_error' if status == 200 else f'http_{status}')

def test_missing_credentials_never_request(monkeypatch):
    monkeypatch.delenv('ALPACA_API_KEY', raising=False)
    monkeypatch.delenv('ALPACA_API_SECRET', raising=False)
    result = capture(AlpacaReader(object()), NOW)
    assert all(result[k]['reason'] == 'credentials_missing' for k in ('quote','bars','news'))
    assert not result['trade_authorized']
