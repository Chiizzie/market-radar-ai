"""Synthetic window-quality probes; no strategy promotion or simulated fills."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
import hashlib
import json

import pytest

from market_radar_ai.market_data.capture import capture_result
from market_radar_ai.market_data.chart_diagnostics import describe, summarize
from market_radar_ai.market_data.models import Candle, ProviderResult, ValidationIssue
from market_radar_ai.market_data.window_recovery import assess, PROTOCOL_ID


NOW = datetime(2026, 11, 10, 17, 0, 1, tzinfo=UTC)


def fixture():
    opening = NOW.replace(hour=14, minute=30, second=0)
    rows = [Candle(symbol='TEST', interval='5m', timestamp=opening+timedelta(minutes=5*i),
                   open='100', high='101', low='99', close='100.5',
                   volume='20000' if i >= 25 else '10000',
                   quote_currency='USD', source='alpaca_iex') for i in range(30)]
    # The missing 09:40 bar is outside the valid most-recent 100-minute window.
    rows.pop(2)
    return ProviderResult(provider='alpaca_iex', retrieved_at=NOW, candles=rows)


def checked(result, *, now=NOW):
    return capture_result(result, now=now)['payload']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def test_gap_outside_window_produces_reproducible_shadow_evidence_only():
    result = fixture()
    original = deepcopy(result.model_dump(mode='json'))
    payload = checked(result)
    before = deepcopy(payload)
    report = assess(result, payload, now=NOW, expected_symbol='TEST')
    assert report['status'] == 'recoverable_data_window'
    assert report['blockers'] == []
    assert report['observed_bars'] == 20 and report['excluded_observed_bars'] == 9
    assert report['window_candles'] == payload['candles'][-20:]
    assert report['source_payload_sha256'] == capture_result(result, now=NOW)['payload_sha256']
    assert report['window_payload_sha256'] == digest(report['window_candles'])
    assert report['window_start_at'] == '2026-11-10T15:20:00+00:00'
    assert report['measurements']['relative_volume_recent_5_vs_previous_15'] == '2'
    assert report['shadow_only'] and not report['trade_authorized']
    assert not report['quality_gates_changed'] and not report['strategy_gates_evaluated']
    assert report['opening_strategy'] == 'not_recovered_full_opening_history_required'
    assert result.model_dump(mode='json') == original and payload == before
    assert payload['quality_passed_at_capture'] is False


@pytest.mark.parametrize('change,reason', [
    ('recent_gap', 'last_20_not_contiguous'),
    ('short', 'fewer_than_20_observed_bars'),
    ('duplicate', 'source_duplicate_bars'),
    ('wrong_symbol', 'source_identity_mismatch'),
    ('wrong_currency', 'source_identity_mismatch'),
    ('wrong_source', 'source_identity_mismatch'),
    ('wrong_interval', 'source_identity_mismatch'),
    ('partial_provider', 'provider_not_clean_iex'),
    ('provider_warning', 'provider_not_clean_iex'),
    ('misaligned', 'bars_not_five_minute_aligned'),
    ('previous_day', 'window_outside_current_session'),
    ('stale', 'latest_bar_incomplete_or_stale'),
    ('incomplete', 'latest_bar_incomplete_or_stale'),
    ('future_retrieval', 'provider_retrieval_in_future'),
    ('unknown_quality', 'original_failure_not_gap_only'),
])
def test_truncation_cannot_conceal_other_failures(change, reason):
    result = fixture()
    now = NOW
    if change == 'recent_gap': result.candles.pop(-3)
    if change == 'short': result.candles[:] = result.candles[:19]
    if change == 'duplicate': result.candles.insert(1, result.candles[0])
    replacements = {'wrong_symbol': {'symbol': 'OTHER'}, 'wrong_currency': {'quote_currency': 'EUR'},
                    'wrong_source': {'source': 'yahoo_finance'}, 'wrong_interval': {'interval': '1m'}}
    if change in replacements:
        # Even a defect outside the recovered window remains disqualifying.
        result.candles[0] = result.candles[0].model_copy(update=replacements[change])
    if change == 'partial_provider': result.status = 'partial'
    if change == 'provider_warning': result.issues.append(ValidationIssue(code='truncated', message='partial reply'))
    if change == 'misaligned':
        result.candles[:] = [r.model_copy(update={'timestamp': r.timestamp-timedelta(seconds=1)}) for r in result.candles]
    if change == 'previous_day':
        result.candles[:] = [r.model_copy(update={'timestamp': r.timestamp-timedelta(days=1)}) for r in result.candles]
    if change == 'stale': now += timedelta(minutes=11)
    if change == 'incomplete': now -= timedelta(minutes=2)
    if change == 'future_retrieval': result.retrieved_at += timedelta(minutes=2)
    payload = checked(result, now=now)
    if change == 'unknown_quality': payload['quality_issues'].append({'code': 'unknown_new_failure'})
    report = assess(result, payload, now=now, expected_symbol='TEST')
    assert report['status'] == 'blocked' and reason in report['blockers']
    assert 'window_candles' not in report and not report['trade_authorized']


def test_zero_volume_is_not_invented_and_does_not_assert_strategy_readiness():
    result = fixture()
    result.candles[:] = [r.model_copy(update={'volume': r.volume*0}) for r in result.candles]
    report = assess(result, checked(result), now=NOW)
    assert report['status'] == 'recoverable_data_window'
    assert report['measurements']['relative_volume_recent_5_vs_previous_15'] is None
    assert report['measurements']['window_vwap_usd'] is None
    assert report['strategy_gates_evaluated'] is False


def test_healthy_history_is_not_counted_as_recovery_and_old_summaries_remain_supported():
    result = fixture()
    result.candles[:] = result.candles[-20:]
    report = assess(result, checked(result), now=NOW)
    assert report['status'] == 'not_needed_full_history_passed'
    summary = summarize([{'symbol': 'TEST', 'chart_diagnostics': {'category': 'usable_iex_history'}}])
    assert summary['window_recovery_shadow']['assessed'] == 0


def test_diagnostic_summary_reports_recoverable_symbols_without_changing_quality_gate():
    result = fixture()
    payload = checked(result)
    diagnostic = describe(result, payload, now=NOW, expected_symbol='TEST')
    summary = summarize([{'symbol': 'TEST', 'chart_diagnostics': diagnostic}])
    assert diagnostic['category'] == 'gapped_iex_history'
    assert summary['gapped_with_contiguous_last_20'] == 1
    shadow = summary['window_recovery_shadow']
    assert shadow['protocol_id'] == PROTOCOL_ID
    assert shadow['recoverable_data_windows'] == 1 and shadow['symbols'] == ['TEST']
    assert not summary['quality_gates_changed'] and not payload['quality_passed_at_capture']


def test_expected_symbol_binding_is_not_inferred_from_provider_rows():
    result = fixture()
    report = assess(result, checked(result), now=NOW, expected_symbol='DIFFERENT')
    assert 'source_identity_mismatch' in report['blockers']


def test_closed_session_does_not_offer_a_recovery_window():
    result = fixture()
    now = NOW.replace(hour=21)
    report = assess(result, checked(result, now=now), now=now)
    assert 'outside_regular_session_hours' in report['blockers']
