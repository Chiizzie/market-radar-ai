"""Regression coverage for PostgreSQL trimming signed timestamp precision."""
from copy import deepcopy

import pytest

from market_radar_ai.agents.comparison_live import EventClient, event_id


def read_event(original, returned, change=None):
    experiment = 'a' * 64
    event = {'experiment_id': experiment, 'day': '2026-11-09', 'seq': 178,
             'kind': 'report', 'occurred_at': original,
             'payload_json': '{"dataset_kind":"forward","trade_authorized":false}'}
    event['event_id'] = event_id(experiment, event)
    event['occurred_at'] = returned
    if change:
        event.update(change)
    untouched = deepcopy(event)
    client = EventClient('x' * 32)
    client.request = lambda body: {'ok': True, 'events': [event], 'next': 178}
    result = client.read(experiment, '2026-11-09', 0)
    assert event == untouched
    assert result['next'] == 178
    assert result['events'][0]['event_id'] == event['event_id']
    return result['events'][0]


@pytest.mark.parametrize('fraction', ['964140', '964100', '964000', '960000', '900000', '000000'])
def test_database_trailing_zeros_preserve_original_hash(fraction):
    original = f'2026-11-09T08:16:08.{fraction}+00:00'
    trimmed = fraction.rstrip('0')
    returned = '2026-11-09T08:16:08' + ('.' + trimmed if trimmed else '') + '+00:00'
    assert read_event(original, returned)['occurred_at'] == original


def test_seconds_only_and_unmodified_timestamps():
    for stamp in ['2026-11-09T08:16:08+00:00', '2026-11-09T08:16:08.964141+00:00']:
        assert read_event(stamp, stamp)['occurred_at'] == stamp


@pytest.mark.parametrize('change', [
    {'payload_json': '{}'}, {'kind': 'quote'}, {'event_id': 'b' * 64},
    {'occurred_at': '2026-11-09T08:16:08.96415+00:00'},
])
def test_format_recovery_still_rejects_tampering(change):
    with pytest.raises(ValueError, match='invalid_comparison_event'):
        read_event('2026-11-09T08:16:08.964140+00:00',
                   '2026-11-09T08:16:08.96414+00:00', change)
