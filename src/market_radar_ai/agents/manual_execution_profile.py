"""Additional OFFLINE admission checks for the user's manual paper test profile.

This module does not create fills, size positions, move stops or manage a book.
Callers must supply dated, reconciled state and still enforce all existing gates.
In particular, a future engine must persist the daily halt latch and reservations.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .candidate_packages import digest


APPROVED_PROFILE_ID = '31cb0c3f4bbcd52fe1c4cf62b4b72fc9113d1ef1368befb4b141c9d00b488b5b'
ZONE = ZoneInfo('Europe/Dublin')
D = Decimal


def validate_profile(raw):
    if not isinstance(raw, dict):
        raise ValueError('invalid_manual_profile')
    body = {k: v for k, v in raw.items() if k != 'profile_id'}
    if raw.get('profile_id') != APPROVED_PROFILE_ID or digest(body) != APPROVED_PROFILE_ID:
        raise ValueError('unapproved_manual_profile')
    return deepcopy(raw)


def amount(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('invalid_risk_amount')
    try:
        result = D(value)
    except (InvalidOperation, ValueError):
        raise ValueError('invalid_risk_amount') from None
    if not result.is_finite() or abs(result) > D('1e12'):
        raise ValueError('invalid_risk_amount')
    return result


def instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone_required')
    return value


def result(profile, reasons, *, unknown=False, **details):
    return {'profile_id': profile['profile_id'],
            'status': 'unknown' if unknown else 'blocked' if reasons else 'profile_checks_passed',
            'reasons': reasons, 'trade_authorized': False, **details}


def risk_gate(raw_profile, *, as_of, state_day, available_capital_eur,
              reserved_risk_eur, today_net_realized_pnl_eur, proposed_capital_eur,
              proposed_risk_eur, active_positions, daily_halt_latched,
              risk_estimate_complete):
    """Check a reconciled snapshot; pending/open/unresolved risk stays reserved.

    Net realized loss is measured against the day's starting balance. Profits do
    not raise either the EUR50 budget or the inherited EUR40 open-risk ceiling.
    The result is an extra gate, never authorization to place an order.
    """
    p = validate_profile(raw_profile)
    today = instant(as_of).astimezone(ZONE).date().isoformat()
    fields = (state_day, available_capital_eur, reserved_risk_eur,
              today_net_realized_pnl_eur, proposed_capital_eur, proposed_risk_eur,
              active_positions, daily_halt_latched, risk_estimate_complete)
    if any(v is None for v in fields):
        return result(p, ['incomplete_risk_state'], unknown=True)
    if state_day != today:
        return result(p, ['risk_state_not_for_current_dublin_day'], unknown=True)
    if type(daily_halt_latched) is not bool or type(risk_estimate_complete) is not bool:
        raise ValueError('invalid_risk_flags')
    if not risk_estimate_complete:
        return result(p, ['incomplete_cost_or_stop_risk'], unknown=True)
    if type(active_positions) is not int or active_positions < 0:
        raise ValueError('invalid_position_count')
    cash, reserved, pnl, capital, proposed = map(amount, fields[1:6])
    if cash < 0 or reserved < 0 or capital <= 0 or proposed <= 0:
        raise ValueError('invalid_risk_state')
    loss = max(D(0), -pnl)
    day_limit = amount(p['maximum_daily_loss_eur'])
    open_limit = amount(p['maximum_combined_open_risk_eur'])
    trade_limit = amount(p['maximum_trade_risk_eur'])
    headroom = max(D(0), min(trade_limit, day_limit - loss - reserved,
                              open_limit - reserved))
    reasons = []
    if daily_halt_latched or loss >= day_limit:
        reasons.append('daily_loss_halt')
    if loss + reserved + proposed > day_limit:
        reasons.append('daily_loss_budget')
    if reserved + proposed > open_limit:
        reasons.append('combined_open_risk_limit')
    if proposed > trade_limit:
        reasons.append('per_trade_risk_limit')
    if capital > cash:
        reasons.append('insufficient_available_capital')
    if capital > amount(p['maximum_allocation_eur']):
        reasons.append('allocation_limit')
    if active_positions >= p['maximum_positions']:
        reasons.append('position_limit')
    if daily_halt_latched:
        headroom = D(0)
    return result(p, reasons, daily_realized_loss_eur=str(loss),
                  remaining_planned_risk_eur=str(headroom),
                  proposed_daily_loss_exposure_eur=str(loss + reserved + proposed))


def timing_gate(raw_profile, *, delay_seconds, as_of, alert_received_at,
                decision_available_at, quote_observed_at, quote_received_at,
                expires_at, exit_by, session_permitted):
    """Assess a received quote after manual readiness; never manufacture a fill.

    A real alert receipt is required. Assembly/enrolment time is not a substitute.
    The quote must be newly observed after both the delay and decision availability.
    """
    p = validate_profile(raw_profile)
    if type(delay_seconds) is not int or delay_seconds not in p['tested_response_delays_seconds']:
        raise ValueError('undeclared_response_scenario')
    if session_permitted is not None and type(session_permitted) is not bool:
        raise ValueError('invalid_session_state')
    clocks = (as_of, alert_received_at, decision_available_at, quote_observed_at,
              quote_received_at, expires_at, exit_by)
    if any(v is None for v in clocks) or session_permitted is None:
        return result(p, ['missing_alert_decision_quote_or_session_evidence'], unknown=True)
    now, alert, decision, observed, received, expiry, exit_at = map(instant, clocks)
    if observed > received:
        return result(p, ['quote_receipt_precedes_observation'], unknown=True)
    if any(t > now for t in (alert, decision, observed, received)):
        return result(p, ['future_evidence'], unknown=True)
    ready = max(alert + timedelta(seconds=delay_seconds), decision)
    local = now.astimezone(ZONE)
    reasons = []
    if not session_permitted:
        reasons.append('session_not_permitted')
    if p['weekdays_only'] and local.weekday() >= 5:
        reasons.append('weekend')
    if local.strftime('%H:%M') >= p['last_entry_local_time']:
        reasons.append('dublin_entry_cutoff')
    if local.date() != alert.astimezone(ZONE).date() or local.date() != exit_at.astimezone(ZONE).date():
        reasons.append('not_same_day_intraday_setup')
    deadline = min(expiry, exit_at - timedelta(seconds=p['exit_buffer_seconds']))
    if ready >= deadline:
        reasons.append('response_exceeds_entry_window')
    if now >= deadline:
        reasons.append('entry_window_expired')
    if now < ready:
        reasons.append('awaiting_manual_response_or_decision')
    if observed < ready:
        reasons.append('quote_predates_manual_readiness')
    if (now - observed).total_seconds() > p['maximum_quote_age_seconds']:
        reasons.append('stale_quote')
    return result(p, reasons, ready_at=ready.isoformat(),
                  entry_deadline=deadline.isoformat(), delay_seconds=delay_seconds)
