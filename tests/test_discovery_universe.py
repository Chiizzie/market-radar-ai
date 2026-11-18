import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from market_radar_ai.market_data.discovery_universe import (
    MAX_CACHE_BYTES,
    MAX_SYMBOLS,
    load_universe,
)

NOW = datetime(2026, 11, 6, 10, tzinfo=UTC)


def row(symbol='AAPL', **changes):
    return SimpleNamespace(ticker=symbol + '_US_EQ', type='STOCK', currencyCode='USD',
                           **changes)


def fail():
    raise RuntimeError('provider failure including secret-token-not-for-output')


def seed(path):
    return load_universe(now=NOW, cache_path=path, fetch=lambda: [row()])


def rewrite(path, change, *, resign=True):
    record = json.loads(path.read_text())
    change(record['payload'])
    if resign:
        record['sha256'] = hashlib.sha256(json.dumps(record['payload'], sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    path.write_text(json.dumps(record))


def test_normalises_exact_stock_identity_and_persists_no_provider_fields(tmp_path):
    path = tmp_path/'universe.json'
    rows = [row('MSFT', name='secret-token-not-for-output'), row(), row(), row('BRK.B'),
            {'ticker':'ZZZ_US_EQ', 'type':'STOCK', 'currencyCode':'USD'},
            {'ticker':'ETF_US_EQ', 'type':'ETF', 'currencyCode':'USD'},
            {'ticker':'EUR_US_EQ', 'type':'STOCK', 'currencyCode':'EUR'},
            {'ticker':'UK_GB_EQ', 'type':'STOCK', 'currencyCode':'USD'},
            {'ticker':'BAD/URL_US_EQ', 'type':'STOCK', 'currencyCode':'USD'},
            {'ticker':'lower_US_EQ', 'type':'STOCK', 'currencyCode':'USD'}, None]
    result = load_universe(now=NOW, cache_path=path, fetch=lambda: rows)
    assert result['symbols'] == ['AAPL', 'BRK.B', 'MSFT', 'ZZZ']
    assert result['cache_status'] == 'refreshed' and result['freshness'] == 'fresh'
    assert result['source'] == 'trading212_metadata' and not result['failures']
    assert result['retrieved_at'] == NOW.isoformat()
    assert not result['account_permission_verified'] and not result['trade_authorized']
    assert 'secret-token' not in path.read_text()
    assert set(json.loads(path.read_text())['payload']) == {
        'schema_version', 'source', 'retrieved_at', 'symbols'}


def test_separate_calls_reuse_file_and_preserve_original_timestamp(tmp_path):
    path = tmp_path/'nested'/'universe.json'
    initial = seed(path)
    initial['symbols'].append('MUTATED')
    restored = load_universe(now=NOW+timedelta(hours=23, minutes=59),
                             cache_path=path, fetch=fail)
    assert restored['symbols'] == ['AAPL']
    assert restored['cache_status'] == 'reused' and restored['freshness'] == 'fresh'
    assert restored['retrieved_at'] == NOW.isoformat() and not restored['failures']


def test_refresh_at_twenty_four_hours_replaces_cache(tmp_path):
    path = tmp_path/'universe.json'
    seed(path)
    later = NOW+timedelta(hours=24)
    fresh = load_universe(now=later, cache_path=path, fetch=lambda: [row('MSFT')])
    assert fresh['symbols'] == ['MSFT'] and fresh['retrieved_at'] == later.isoformat()
    assert fresh['cache_status'] == 'refreshed'
    assert load_universe(now=later, cache_path=path, fetch=fail)['symbols'] == ['MSFT']


@pytest.mark.parametrize('hours', [24, 48, 72])
def test_failed_refresh_reuses_grace_period_without_redating(tmp_path, hours):
    path = tmp_path/'universe.json'
    seed(path)
    before = path.read_bytes()
    cached = load_universe(now=NOW+timedelta(hours=hours), cache_path=path, fetch=fail)
    assert cached['symbols'] == ['AAPL'] and cached['cache_status'] == 'reused'
    assert cached['freshness'] == 'stale_but_valid'
    assert cached['retrieved_at'] == NOW.isoformat()
    assert cached['failures'] == ['universe_refresh_failed']
    assert path.read_bytes() == before and 'secret-token' not in str(cached)


def test_cache_older_than_seventy_two_hours_never_substitutes_for_failed_refresh(tmp_path):
    path = tmp_path/'universe.json'
    seed(path)
    result = load_universe(now=NOW+timedelta(hours=72, seconds=1),
                           cache_path=path, fetch=fail)
    assert result['symbols'] == [] and result['retrieved_at'] is None
    assert result['cache_status'] == result['freshness'] == 'unavailable'
    assert result['failures'] == ['universe_cache_expired', 'universe_refresh_failed']


@pytest.mark.parametrize('change,resign', [
    (lambda p: p.update(symbols=['MSFT']), False),
    (lambda p: p.update(source='other_provider'), True),
    (lambda p: p.update(schema_version='other_schema'), True),
    (lambda p: p.update(retrieved_at=(NOW+timedelta(seconds=1)).isoformat()), True),
    (lambda p: p.update(retrieved_at=NOW.replace(tzinfo=None).isoformat()), True),
    (lambda p: p.update(symbols=['MSFT', 'AAPL']), True),
    (lambda p: p.update(symbols=['AAPL', 'AAPL']), True),
    (lambda p: p.update(symbols=['BAD/URL']), True),
    (lambda p: p.update(symbols=[]), True),
    (lambda p: p.update(symbols=['S'+str(i) for i in range(MAX_SYMBOLS+1)]), True),
    (lambda p: p.update(credentials='must_not_be_accepted'), True),
])
def test_invalid_or_tampered_cache_does_not_supply_candidates(tmp_path, change, resign):
    path = tmp_path/'universe.json'
    seed(path)
    rewrite(path, change, resign=resign)
    result = load_universe(now=NOW, cache_path=path, fetch=fail)
    assert not result['symbols'] and result['retrieved_at'] is None
    assert 'universe_cache_invalid' in result['failures']


@pytest.mark.parametrize('data,code', [
    (b'{broken', 'universe_cache_invalid'),
    (b'\xff', 'universe_cache_invalid'),
    (b'['*2000 + b']'*2000, 'universe_cache_invalid'),
    (b'x'*(MAX_CACHE_BYTES+1), 'universe_cache_oversize'),
])
def test_bounded_corrupt_cache_reads_recover_from_fresh_catalogue(tmp_path, data, code):
    path = tmp_path/'universe.json'
    path.write_bytes(data)
    result = load_universe(now=NOW, cache_path=path, fetch=lambda: [row()])
    assert result['symbols'] == ['AAPL'] and result['cache_status'] == 'refreshed'
    assert result['failures'] == [code]
    assert load_universe(now=NOW, cache_path=path, fetch=fail)['cache_status'] == 'reused'


@pytest.mark.parametrize('now', [NOW.replace(tzinfo=None), None, '2026-11-06'])
def test_invalid_clock_fails_before_fetch(now):
    with pytest.raises(ValueError, match='aware_clock_required'):
        load_universe(now=now, fetch=fail)


@pytest.mark.parametrize('rows', [[], None, [row('S'+str(i)) for i in range(MAX_SYMBOLS+1)]])
def test_empty_invalid_or_oversize_fresh_universe_is_unavailable(rows):
    result = load_universe(now=NOW, fetch=lambda: rows)
    assert result['symbols'] == [] and result['cache_status'] == 'unavailable'
    assert result['failures'] == ['universe_refresh_failed']


def test_cache_write_failure_retains_fresh_result_and_previous_file(tmp_path, monkeypatch):
    path = tmp_path/'universe.json'
    seed(path)
    original = path.read_bytes()
    def fail_replace(*args):
        raise OSError('atomic replace unavailable')
    monkeypatch.setattr('market_radar_ai.market_data.discovery_universe.os.replace', fail_replace)
    result = load_universe(now=NOW+timedelta(hours=24), cache_path=path,
                           fetch=lambda: [row('MSFT')])
    assert result['symbols'] == ['MSFT'] and result['cache_status'] == 'refreshed'
    assert result['failures'] == ['universe_cache_write_failed']
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_default_provider_is_used_without_persisting_credentials(monkeypatch):
    monkeypatch.setattr('market_radar_ai.market_data.providers.catalogues.Trading212Catalogue.fetch',
                        lambda self: [row()])
    assert load_universe(now=NOW)['symbols'] == ['AAPL']
