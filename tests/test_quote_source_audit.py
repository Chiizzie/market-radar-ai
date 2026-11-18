from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
import requests

from market_radar_ai.market_data.quote_source_audit import run, fetch_feed, classify_quote, URL

NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)
ENV = {'ALPACA_API_KEY': 'offline-key', 'ALPACA_API_SECRET': 'offline-secret'}


def quote(age=0, **changes):
    return {'t': (NOW-timedelta(seconds=age)).isoformat(), 'bp': 100, 'ap': 100.1,
            'bs': 10, 'as': 10, **changes}


class Response:
    def __init__(self, code, payload):
        self.status_code, self.payload = code, payload
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, _): yield json.dumps(self.payload).encode()


class Transport:
    def __init__(self, responses):
        self.responses, self.calls = responses, []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses[kwargs['params']['feed']]
        if isinstance(response, Exception): raise response
        return response


@pytest.mark.parametrize('age,changes,expected', [
    (0, {}, 'current_reference_quote'), (30, {}, 'current_reference_quote'),
    (30.001, {}, 'stale_quote'), (-.01, {}, 'future_quote'),
    (0, {'bp': 101}, 'crossed_quote'), (0, {'ap': 101}, 'wide_reference_quote'),
    (0, {'bp': 'NaN'}, 'invalid_price_or_size'), (0, {'as': 0}, 'invalid_price_or_size'),
    (0, {'t': '2026-11-13'}, 'malformed_quote'),
])
def test_timestamp_price_size_and_spread_rules_are_not_relaxed(age, changes, expected):
    row = classify_quote('SPY', {'quotes': {'SPY': quote(age, **changes)}}, received=NOW)
    assert row['state'] == expected


def test_quote_rows_fail_independently_and_retain_source_times():
    payload = {'quotes': {'SPY': quote(), 'OCUL': quote(95)}}
    assert classify_quote('SPY', payload, received=NOW)['state'] == 'current_reference_quote'
    row = classify_quote('OCUL', payload, received=NOW)
    assert row['state'] == 'stale_quote' and row['age_seconds'] == 95
    assert row['quote_at'] != row['received_at']
    assert classify_quote('MFG', payload, received=NOW)['state'] == 'missing_quote'


def test_entitlement_refusal_is_bounded_and_never_logged_as_raw_provider_text():
    t = Transport({'iex': Response(200, {'quotes': {'SPY': quote(), 'OCUL': quote(50)}}),
                   'sip': Response(403, {'code': 42210000,
                      'message': 'subscription does not permit querying recent SIP data offline-secret'})})
    health = {'comparison': {'recent_quote_failures': [{'symbol': 'OCUL', 'reason': 'stale_quote'}]}}
    before = deepcopy(health)
    waits = []
    r = run(health, env=ENV, transport=t, clock=lambda: NOW, sleep=waits.append)
    assert health == before and r['symbols'] == ['SPY', 'OCUL']
    assert r['feeds']['sip']['requests'] == 1 and r['feeds']['iex']['requests'] == 3
    assert r['feeds']['sip']['request_states'] == {'subscription_not_permitted': 3}
    assert r['feeds']['iex']['quote_states']['stale_quote'] == 3
    assert waits == [5, 5] and r['strategy_input'] is False and r['trade_authorized'] is False
    assert 'offline-secret' not in json.dumps(r)
    assert all(url == URL and kw['allow_redirects'] is False for url, kw in t.calls)


@pytest.mark.parametrize('code,payload,state', [
    (403, {'message': 'not authorized offline-secret'}, 'forbidden_unclassified'),
    (401, {'message': 'offline-secret'}, 'authentication_rejected'),
    (429, {'message': 'offline-secret'}, 'rate_limited'),
    (503, {'message': 'offline-secret'}, 'provider_http_error'),
    (200, ['malformed'], 'invalid_payload'),
])
def test_http_refusals_do_not_guess_subscription_or_print_credentials(code, payload, state):
    t = Transport({'sip': Response(code, payload)})
    r = fetch_feed('sip', ['SPY'], env=ENV, transport=t, clock=lambda: NOW)
    assert r['state'] == state and 'offline-secret' not in json.dumps(r)


def test_available_alternative_is_only_a_paired_diagnostic_not_a_fallback():
    t = Transport({'iex': Response(200, {'quotes': {'SPY': quote(80)}}),
                   'sip': Response(200, {'quotes': {'SPY': quote(0, bp=100.05, ap=100.06)}})})
    r = run({}, env=ENV, transport=t, clock=lambda: NOW, sleep=lambda _: None)
    assert len(t.calls) == 6 and all(pair['iex_state'] == 'stale_quote' for pair in r['pairs'])
    assert all(pair['sip_state'] == 'current_reference_quote' for pair in r['pairs'])
    assert all('sip_minus_iex_mid_bps' in pair for pair in r['pairs'])
    assert r['model_calls'] == 0 and r['strategy_input'] is False


def test_symbol_selection_is_bounded_and_cannot_inject_network_targets():
    t = Transport({'iex': Response(200, {'quotes': {}}), 'sip': Response(200, {'quotes': {}})})
    failures = [{'symbol': f'ABC{i}'} for i in range(30)]+[{'symbol': 'https://private.example/key'}]
    r = run({'recent_quote_failures': failures}, env=ENV, transport=t, clock=lambda: NOW, sleep=lambda _: None)
    assert len(r['symbols']) == 8 and r['symbols'][0] == 'SPY'
    assert all('https' not in symbol for symbol in r['symbols'])
    assert all(url == URL for url, _ in t.calls)


def test_audit_rejects_paid_or_mutating_credentials_before_network():
    t = Transport({})
    with pytest.raises(ValueError, match='unneeded_credentials'):
        run({}, env={**ENV, 'GH_BUDGET_TOKEN': 'do-not-use'}, transport=t)
    assert t.calls == []


def test_transport_failure_retains_unknown_data():
    t = Transport({'iex': requests.Timeout('offline-secret')})
    result = fetch_feed('iex', ['SPY'], env=ENV, transport=t, clock=lambda: NOW)
    assert result == {'feed': 'iex', 'state': 'transport_unavailable', 'rows': []}
