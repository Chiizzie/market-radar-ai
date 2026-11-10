"""Measure a usable momentum window without relaxing the live chart gate.

This is a prospective data-quality experiment, not a trading strategy. Only a
gap outside the last 20 observed bars may be bypassed in this shadow assessment.
Opening/session-anchored strategies still need their original complete history.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import ProviderResult

PROTOCOL_ID = 'contiguous_20bar_recovery_shadow_v1'


def _digest(value):
    canonical = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def assess(result, checked, *, now, expected_symbol=None):
    """Return auditable, unmodified window evidence; never authorize selection.

    Provider failures, non-gap quality issues and identity errors cannot be
    repaired by truncating history. Exact five-minute alignment, completion,
    freshness and current-session bounds are required independently of the
    existing full-history validator.
    """
    report = {
        'protocol_id': PROTOCOL_ID,
        'shadow_only': True,
        'trade_authorized': False,
        'quality_gates_changed': False,
        'strategy_gates_evaluated': False,
        'opening_strategy': 'not_recovered_full_opening_history_required',
        'status': 'blocked',
        'blockers': [],
    }
    if not isinstance(result, ProviderResult):
        report['blockers'] = ['provider_result_unavailable']
        return report
    rows = sorted(result.candles, key=lambda row: row.timestamp)[-60:]
    symbol = expected_symbol or (rows[-1].symbol if rows else None)
    report.update(symbol=symbol, source_payload_sha256=_digest(checked),
                  source_retrieved_at=result.retrieved_at.isoformat(),
                  assessed_at=now.isoformat())
    blockers = report['blockers']
    codes = {issue.get('code', 'unknown') for issue in checked.get('quality_issues', [])}
    if checked.get('quality_passed_at_capture'):
        report['status'] = 'not_needed_full_history_passed'
        return report
    if result.status != 'ok' or result.provider != 'alpaca_iex' or result.issues:
        blockers.append('provider_not_clean_iex')
    if codes != {'candle_gap'}:
        blockers.append('original_failure_not_gap_only')
    # Keep source identity checks over the whole captured history. Truncation
    # must not conceal a provider/symbol/currency mapping defect.
    if not symbol or any(row.symbol != symbol or row.source != 'alpaca_iex'
                         or row.quote_currency != 'USD' or row.interval != '5m' for row in rows):
        blockers.append('source_identity_mismatch')
    keys = [(row.symbol, row.interval, row.source, row.timestamp) for row in rows]
    if len(set(keys)) != len(keys):
        blockers.append('source_duplicate_bars')
    if len(rows) < 20:
        blockers.append('fewer_than_20_observed_bars')
    window = rows[-20:]
    if any((b.timestamp-a.timestamp).total_seconds() != 300 for a, b in zip(window, window[1:])):
        blockers.append('last_20_not_contiguous')
    if any(row.timestamp.second or row.timestamp.microsecond or row.timestamp.minute % 5 for row in window):
        blockers.append('bars_not_five_minute_aligned')
    if now.tzinfo is None or result.retrieved_at.tzinfo is None:
        blockers.append('timestamps_not_timezone_aware')
    else:
        local = now.astimezone(ZoneInfo('America/New_York'))
        opening = local.replace(hour=9, minute=30, second=0, microsecond=0)
        close = opening.replace(hour=16, minute=0)
        if local.weekday() >= 5 or not opening <= local < close:
            blockers.append('outside_regular_session_hours')
        if any(row.timestamp < opening or row.timestamp + timedelta(minutes=5) > close for row in window):
            blockers.append('window_outside_current_session')
        if window and not 300 <= (now-window[-1].timestamp).total_seconds() <= 900:
            blockers.append('latest_bar_incomplete_or_stale')
        if (now-result.retrieved_at).total_seconds() < -60:
            blockers.append('provider_retrieval_in_future')
    if any(not value.is_finite() for row in rows
           for value in (row.open, row.high, row.low, row.close, row.volume)):
        blockers.append('nonfinite_source_values')
    if blockers:
        return report

    evidence = [row.model_dump(mode='json') for row in window]
    earlier_volume = sum(row.volume for row in window[:-5]) / Decimal(15)
    recent_volume = sum(row.volume for row in window[-5:]) / Decimal(5)
    total_volume = sum(row.volume for row in window)
    vwap = (sum((row.high+row.low+row.close)/3*row.volume for row in window) / total_volume
            if total_volume > 0 else None)
    report.update(
        status='recoverable_data_window',
        window_payload_sha256=_digest(evidence),
        window_start_at=window[0].timestamp.isoformat(),
        window_end_at=window[-1].timestamp.isoformat(),
        observed_bars=20,
        excluded_observed_bars=len(rows)-20,
        window_candles=evidence,
        measurements={
            'momentum_pct': str((window[-1].close/window[0].close-1)*100),
            'relative_volume_recent_5_vs_previous_15': str(recent_volume/earlier_volume) if earlier_volume > 0 else None,
            'window_vwap_usd': str(vwap) if vwap is not None else None,
            'last_close_usd': str(window[-1].close),
        },
        remaining_checks='Strategy, broker eligibility, catalyst, quote, spread, costs, portfolio risk and AI review are not evaluated.',
    )
    return report
