from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from market_radar_ai.agents.github_budget import initial_state
from market_radar_ai.dashboard.api_budget import read_summary, summarize, validate_summary
from market_radar_ai.dashboard.export import build_snapshot
from test_dashboard_cache import capture

NOW = datetime(2026, 11, 6, 16, tzinfo=timezone.utc)


def ledger():
    state = initial_state()
    usage = dict(response_id='private-response', model='test', input_tokens=20,
        output_tokens=10, cached_input_tokens=0, cost_usd='0.05', eur_per_usd='0.9',
        pricing_checked='2026-11-02')
    state['entries'] = {
        'old': dict(day='2026-10-01', reserved=200000, actual=100000, usage=usage),
        'month': dict(day='2026-11-01', reserved=200000, actual=100000, usage=usage),
        'today': dict(day='2026-11-06', reserved=100000, actual=42661, usage=usage),
        'pending': dict(day='2026-11-06', reserved=80000, actual=None, usage=None),
        'marker': dict(day='2026-11-06', reserved=1, actual=0, usage=None),
    }
    return state


def test_periods_preserve_pending_amounts_and_exclude_markers_from_call_count():
    state = ledger()
    before = deepcopy(state)
    result = summarize(state, now=NOW)
    assert state == before
    today = result['periods']['daily']
    assert today == dict(settled_microeur=42661, reserved_microeur=80000,
        limit_microeur=1000000, remaining_microeur=877339, completed_calls=1,
        unsettled_reservations=1)
    assert result['periods']['monthly']['settled_microeur'] == 142661
    assert result['periods']['lifetime']['settled_microeur'] == 242661
    assert 'private-response' not in json.dumps(result)
    assert 'entries' not in result and 'usage' not in result


def test_day_rollover_uses_dublin_summer_time():
    state = initial_state()
    state['entries']['test'] = dict(day='2026-07-02', reserved=25, actual=10, usage=None)
    result = summarize(state, now=datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc))
    assert result['budget_day'] == '2026-07-02'
    assert result['periods']['daily']['settled_microeur'] == 10


def test_read_only_failure_reports_unknown_not_zero_or_error_details():
    class Store:
        def load(self):
            raise RuntimeError('private-key')
    result = read_summary('token', clock=lambda: NOW, store_factory=lambda token: Store())
    assert result['status'] == 'unavailable' and result['periods'] is None
    assert 'private-key' not in json.dumps(result)
    assert read_summary(None, clock=lambda: NOW) == result
    class GoodStore:
        def load(self):
            return ledger(), 'private-sha'
    assert read_summary('token', clock=lambda: NOW, store_factory=lambda token: GoodStore()) == summarize(ledger(), now=NOW)


@pytest.mark.parametrize('fault', ['extra', 'amount', 'clock', 'day', 'status', 'periods', 'bool'])
def test_summary_rejects_tampered_or_stale_aggregates(fault):
    value = summarize(ledger(), now=NOW)
    if fault == 'extra': value['api_key'] = 'private'
    if fault == 'amount': value['periods']['daily']['remaining_microeur'] += 1
    if fault == 'clock': value['as_of'] = '2026-11-06T15:50:00+00:00'
    if fault == 'day': value['budget_day'] = '2026-11-05'
    if fault == 'status': value['status'] = 'unavailable'
    if fault == 'periods': value['periods']['daily']['completed_calls'] = 100
    if fault == 'bool': value['periods']['daily']['settled_microeur'] = True
    with pytest.raises(ValueError): validate_summary(value, now=NOW)


def test_export_keeps_usage_aggregates_without_changing_trade_gates():
    doc = capture()
    doc['api_budget'] = summarize(ledger(), now=NOW)
    snapshot = build_snapshot(doc, now=NOW)
    assert snapshot['api_budget'] == doc['api_budget']
    assert snapshot['paper_outcomes'] is None and not snapshot['live_orders_enabled']
    assert all(r['decision'] == 'NO_ACTION' for rows in snapshot['markets'].values() for r in rows)
