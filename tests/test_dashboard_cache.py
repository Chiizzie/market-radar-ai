from datetime import timedelta
from test_market_capture import NOW, result
from market_radar_ai.market_data.cache import CandleCache
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.dashboard.export import build_snapshot
import pytest


def test_cache_expires_and_does_not_relabel_timestamp():
    cache = CandleCache(ttl_seconds=30)
    original = result()
    assert cache.put('kraken', 'XBTEUR', original, now=NOW)
    cached = cache.get('kraken', 'XBTEUR', now=NOW+timedelta(seconds=29))
    assert cached.retrieved_at == NOW
    cached.candles.clear()
    assert cache.get('kraken', 'XBTEUR', now=NOW).candles
    assert cache.get('kraken', 'XBTEUR', now=NOW+timedelta(seconds=30)) is None


def test_cache_invalidates_failure_and_rejects_stale_or_wrong_identity():
    cache = CandleCache()
    assert not cache.put('kraken', 'XBTEUR', result(age=1200), now=NOW)
    assert not cache.put('kraken', 'ETHEUR', result(), now=NOW)
    cache.put('kraken', 'XBTEUR', result(), now=NOW)
    assert not cache.put('kraken', 'XBTEUR', result(status='error'), now=NOW)
    assert cache.get('kraken', 'XBTEUR', now=NOW) is None


def capture():
    return capture_markets([], ['XBTEUR'], stock_fetch=None, crypto_fetch=lambda _: result(), now=NOW)


def test_dashboard_rechecks_age_and_never_grants_eligibility():
    doc = capture()
    fresh = build_snapshot(doc, now=NOW)
    assert fresh['markets']['crypto'][0]['status'] == 'CURRENT_RESEARCH_DATA'
    assert fresh['markets']['crypto'][0]['decision'] == 'NO_ACTION'
    assert fresh['api_budget'] is None
    stale = build_snapshot(doc, now=NOW+timedelta(minutes=20))
    assert stale['markets']['crypto'][0]['status'] == 'UNUSABLE_OR_STALE'


def test_dashboard_rejects_tampering_and_excludes_extra_fields():
    doc = capture()
    doc['secret'] = 'must-not-appear'
    assert 'must-not-appear' not in str(build_snapshot(doc, now=NOW))
    doc['captures'][0]['payload']['provider_status'] = 'error'
    with pytest.raises(ValueError, match='checksum'):
        build_snapshot(doc, now=NOW)


def test_repeated_capture_uses_cache_but_expiry_refetches():
    calls = []
    def fetch(symbol):
        calls.append(symbol)
        return result()
    cache = CandleCache()
    for seconds in (0, 10, 31):
        doc = capture_markets([], ['XBTEUR'], stock_fetch=None, crypto_fetch=fetch,
            now=NOW+timedelta(seconds=seconds), cache=cache)
        assert doc['captures'][0]['cache_hit'] == (seconds == 10)
    assert calls == ['XBTEUR', 'XBTEUR']


def test_dashboard_counts_do_not_imply_agent_reviews():
    doc = capture()
    doc['queue_selection'] = {'crypto': {'selected':['XBTEUR'], 'universe_count':50,'deferred_count':49}}
    p = build_snapshot(doc,now=NOW)
    assert p['coverage']['crypto'] == dict(universe_count=50, attempted=1,deferred=49,
        current=1,unusable_or_stale=0,agent_reviewed=0)
    doc['queue_selection']['crypto']['deferred_count'] = 0
    with pytest.raises(ValueError,match='coverage'):
        build_snapshot(doc,now=NOW)


def test_dashboard_rejects_inconsistent_capture_counts():
    doc = capture()
    doc['coverage']['crypto']['attempted'] = 10
    with pytest.raises(ValueError,match='coverage'):
        build_snapshot(doc,now=NOW)
