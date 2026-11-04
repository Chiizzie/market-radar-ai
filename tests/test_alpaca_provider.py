from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import pytest

from market_radar_ai.market_data.providers.alpaca import AlpacaIexProvider
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.market_data.capture_shortlist import shortlist

NOW = datetime(2026, 11, 4, 16, 10, tzinfo=timezone.utc)
ENV = {'ALPACA_API_KEY': 'private-key', 'ALPACA_API_SECRET': 'private-secret'}


def payload(symbol='MSFT', count=20):
    return {'symbol': symbol, 'bars': [dict(t=(NOW-timedelta(minutes=100-5*i)).isoformat(),
        o=100, h=102, l=99, c=101, v=100+i) for i in range(count)], 'next_page_token': None}


class Session:
    def __init__(self, data=None, status=200):
        self.data = payload() if data is None else data
        self.status = status
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        owner = self
        class Response:
            status_code = owner.status
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_content(self, *args): yield json.dumps(owner.data).encode()
        return Response()


def provider(session=None, now=NOW, env=ENV):
    return AlpacaIexProvider(session=session or Session(), env=env, clock=lambda: now)


def test_generic_stock_enters_pipeline_as_iex_without_other_broker_claims():
    s = Session()
    data = capture_markets(['MSFT'], [], stock_fetch=provider(s).fetch_history,
        crypto_fetch=None, now=NOW, stock_provider='alpaca_iex')
    row = shortlist(data, now=NOW)['markets']['stocks']['candidates'][0]
    assert row['symbol'] == 'MSFT' and row['broker_eligibility'] == 'UNKNOWN'
    assert not row['trade_authorized'] and row['quote_currency'] == 'USD'
    assert data['captures'][0]['payload']['provider'] == 'alpaca_iex'
    url, kw = s.calls[0]
    assert url == 'https://data.alpaca.markets/v2/stocks/MSFT/bars'
    assert kw['allow_redirects'] is False and kw['stream'] is True
    assert kw['params']['feed'] == 'iex' and kw['params']['asof'] == '-'
    assert kw['params']['currency'] == 'USD' and len(s.calls) == 1
    from market_radar_ai.agents.candidate_packages import build_packages
    package = build_packages(data, None, now=NOW)['packages'][0]['package']
    assert 'iex_limited_market_coverage' in package['missing_evidence']
    assert 'fresh_fx_conversion_missing' in package['missing_evidence']


@pytest.mark.parametrize('fault', ['wrong_symbol', 'missing_bars', 'pagination', 'unordered',
    'duplicate', 'future', 'outside_session', 'nan', 'invalid_ohlc', 'unaligned'])
def test_bad_provider_payload_never_enters_candidate_pool(fault):
    p = payload()
    if fault == 'wrong_symbol': p['symbol'] = 'NVDA'
    if fault == 'missing_bars': del p['bars']
    if fault == 'pagination': p['next_page_token'] = 'private-secret'
    if fault == 'unordered': p['bars'].reverse()
    if fault == 'duplicate': p['bars'].append(deepcopy(p['bars'][-1]))
    if fault == 'future': p['bars'][-1]['t'] = (NOW+timedelta(minutes=5)).isoformat()
    if fault == 'outside_session': p['bars'][0]['t'] = (NOW-timedelta(hours=8)).isoformat()
    if fault == 'nan': p['bars'][0]['c'] = 'NaN'
    if fault == 'invalid_ohlc': p['bars'][0]['h'] = 1
    if fault == 'unaligned': p['bars'][0]['t'] = (NOW-timedelta(minutes=99)).isoformat()
    r = provider(Session(p)).fetch_history('MSFT')
    assert r.status == 'error' and not r.candles
    assert 'private-secret' not in r.model_dump_json()


@pytest.mark.parametrize('status', [401, 403, 429, 302, 500])
def test_http_failure_does_not_retry_redirect_or_leak(status):
    s = Session(status=status)
    r = provider(s).fetch_history('MSFT')
    assert r.status == 'error' and len(s.calls) == 1
    assert 'private' not in r.model_dump_json()


def test_no_network_without_credentials_or_for_invalid_symbol():
    s = Session()
    assert provider(s, env={}).fetch_history('MSFT').status == 'error'
    assert provider(s).fetch_history('../orders').status == 'error'
    assert not s.calls


def test_preopen_and_weekend_do_not_request_or_reuse_yesterday():
    for when in (NOW.replace(hour=13), NOW+timedelta(days=3)):
        s = Session()
        r = provider(s, now=when).fetch_history('MSFT')
        assert not r.candles and not s.calls


def test_unfinished_bar_excluded_and_history_warmup_visible():
    p = payload(count=21)
    r = provider(Session(p), now=NOW+timedelta(minutes=2)).fetch_history('MSFT')
    assert r.status == 'ok' and len(r.candles) == 20
    r = provider(Session(payload(count=19))).fetch_history('MSFT')
    d = capture_markets(['MSFT'], [], stock_fetch=lambda _: r, crypto_fetch=None, now=NOW)
    assert shortlist(d, now=NOW)['markets']['stocks']['rejected'][0]['reason'] == 'insufficient_history'


def test_after_close_data_is_retained_but_never_fresh():
    r = provider(now=NOW.replace(hour=22)).fetch_history('MSFT')
    assert r.status == 'ok' and len(r.candles) == 20
    d = capture_markets(['MSFT'], [], stock_fetch=lambda _: r, crypto_fetch=None, now=NOW.replace(hour=22))
    assert shortlist(d, now=NOW.replace(hour=22))['markets']['stocks']['rankable'] == 0


def test_body_limit_and_transport_exception_sanitized():
    class Large(Session):
        def get(self, *args, **kwargs):
            r = super().get(*args, **kwargs)
            r.iter_content = lambda *_: iter([b'x'*1_000_001])
            return r
    assert provider(Large()).fetch_history('MSFT').issues[0].code == 'response_too_large'
    class Broken:
        def get(self, *args, **kwargs): raise RuntimeError('private-secret')
    r = provider(Broken()).fetch_history('MSFT')
    assert r.status == 'error' and 'private' not in r.model_dump_json()


def test_cache_namespace_uses_selected_stock_provider():
    seen = []
    class Cache:
        def get(self, name, symbol, **kw): seen.append(name)
        def put(self, name, symbol, result, **kw): seen.append(name)
    capture_markets(['MSFT'], [], stock_fetch=provider().fetch_history, crypto_fetch=None,
        now=NOW, stock_provider='alpaca_iex', cache=Cache())
    assert seen == ['alpaca_iex', 'alpaca_iex']


def test_preopen_capture_is_explicitly_skipped_not_successful_or_actionable():
    now = NOW.replace(hour=10)
    d = capture_markets(['MSFT'], [], stock_fetch=provider(now=now).fetch_history,
        crypto_fetch=None, now=now, stock_provider='alpaca_iex')
    assert d['coverage']['stocks']['not_requested'] == 1
    assert d['coverage']['stocks']['successful'] == 0
    assert not d['captures'][0]['payload']['quality_passed_at_capture']
    assert d['captures'][0]['payload']['disposition'] == 'NO_ACTION'


def test_open_session_empty_and_auth_failure_are_not_excused():
    for p in (provider(Session({'symbol':'MSFT','bars':[]})), provider(now=NOW.replace(hour=10),env={})):
        d = capture_markets(['MSFT'], [], stock_fetch=p.fetch_history,
            crypto_fetch=None, now=NOW, stock_provider='alpaca_iex')
        assert d['coverage']['stocks']['not_requested'] == 0
        assert d['coverage']['stocks']['successful'] == 0


def test_capture_cli_preopen_success_and_unexpected_empty_failure(tmp_path, monkeypatch):
    import sys
    from market_radar_ai.market_data.capture import main
    from market_radar_ai.market_data.providers.kraken import KrakenProvider
    from market_radar_ai.market_data.models import ProviderResult
    monkeypatch.setattr(KrakenProvider, 'fetch_ohlc', lambda *a, **k: ProviderResult(
        provider='kraken', retrieved_at=NOW, status='error'))
    # Empty crypto selection via universe keeps this regression specific to stocks.
    universe = tmp_path/'universe.json'
    universe.write_text(json.dumps({'stocks':['MSFT'], 'crypto':[]}))
    monkeypatch.setattr(sys, 'argv', ['capture', '--output', str(tmp_path/'capture.json'),
        '--stock-provider', 'alpaca_iex', '--universe', str(universe), '--queue-db', str(tmp_path/'queue.db')])
    skip = provider(now=NOW.replace(hour=10)).fetch_history('MSFT')
    monkeypatch.setattr(AlpacaIexProvider, 'fetch_history', lambda *a: skip)
    assert main() == 0
    monkeypatch.setattr(AlpacaIexProvider, 'fetch_history', lambda *a: ProviderResult(
        provider='alpaca_iex', retrieved_at=NOW))
    assert main() == 1
