import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.manual_execution_profile import (
    APPROVED_PROFILE_ID, risk_gate, timing_gate, validate_profile,
)


PROFILE_PATH = Path(__file__).resolve().parents[1] / 'config/research/manual-execution-20261113.json'
PROFILE = json.loads(PROFILE_PATH.read_text())
NOW = datetime(2026, 11, 16, 15, tzinfo=UTC)


def risk(**changes):
    args = dict(as_of=NOW, state_day='2026-11-16', available_capital_eur='1000',
                reserved_risk_eur='0', today_net_realized_pnl_eur='0',
                proposed_capital_eur='400', proposed_risk_eur='20', active_positions=0,
                daily_halt_latched=False, risk_estimate_complete=True)
    args.update(changes)
    return risk_gate(PROFILE, **args)


def timing(delay=60, **changes):
    at = NOW + timedelta(seconds=delay)
    args = dict(delay_seconds=delay, as_of=at, alert_received_at=NOW,
                decision_available_at=NOW, quote_observed_at=at, quote_received_at=at,
                expires_at=NOW + timedelta(minutes=6), exit_by=NOW + timedelta(hours=1),
                session_permitted=True)
    args.update(changes)
    return timing_gate(PROFILE, **args)


def test_approved_user_profile_is_exact_and_independent_from_runtime_protocol():
    assert validate_profile(PROFILE)['profile_id'] == APPROVED_PROFILE_ID
    assert PROFILE['initial_capital_eur'] == '1000'
    assert PROFILE['maximum_daily_loss_eur'] == '50'
    assert PROFILE['tested_response_delays_seconds'] == [60, 180, 300]
    assert PROFILE['status'] == 'offline_test_profile_not_deployed'
    assert not PROFILE['trade_authorized'] and not PROFILE['runtime_changed']


def test_changed_limits_are_not_approved_by_merely_rehashing():
    altered = deepcopy(PROFILE)
    altered['maximum_daily_loss_eur'] = '500'
    altered['profile_id'] = digest({k: v for k, v in altered.items() if k != 'profile_id'})
    with pytest.raises(ValueError, match='unapproved_manual_profile'):
        validate_profile(altered)


def test_per_trade_cap_and_daily_headroom_after_losses():
    assert risk()['status'] == 'profile_checks_passed'
    after_loss = risk(today_net_realized_pnl_eur='-40')
    assert after_loss['status'] == 'blocked'
    assert after_loss['remaining_planned_risk_eur'] == '10'
    assert after_loss['reasons'] == ['daily_loss_budget']
    smaller = risk(today_net_realized_pnl_eur='-40', proposed_risk_eur='10')
    assert smaller['status'] == 'profile_checks_passed'
    assert not smaller['trade_authorized']
    assert 'per_trade_risk_limit' in risk(proposed_risk_eur='20.01')['reasons']


def test_daily_budget_includes_pending_open_and_unresolved_reservations():
    out = risk(today_net_realized_pnl_eur='-20', reserved_risk_eur='20',
               proposed_risk_eur='15', active_positions=1)
    assert out['reasons'] == ['daily_loss_budget']
    assert out['proposed_daily_loss_exposure_eur'] == '55'
    assert out['remaining_planned_risk_eur'] == '10'


def test_existing_combined_open_risk_cap_remains_40():
    assert risk(reserved_risk_eur='20', active_positions=1)['status'] == 'profile_checks_passed'
    out = risk(reserved_risk_eur='30', proposed_risk_eur='15', active_positions=2)
    assert out['reasons'] == ['combined_open_risk_limit']
    assert out['remaining_planned_risk_eur'] == '10'


@pytest.mark.parametrize('pnl', ['0', '100'])
def test_wins_do_not_increase_risk_ceiling_or_release_a_persisted_day_halt(pnl):
    assert risk(today_net_realized_pnl_eur=pnl)['remaining_planned_risk_eur'] == '20'
    out = risk(today_net_realized_pnl_eur=pnl, daily_halt_latched=True)
    assert out['reasons'] == ['daily_loss_halt']
    assert out['remaining_planned_risk_eur'] == '0'


def test_daily_loss_threshold_blocks_new_risk_without_claiming_a_guaranteed_fill_loss():
    assert 'daily_loss_halt' in risk(today_net_realized_pnl_eur='-50')['reasons']
    assert 'daily_loss_halt' in risk(today_net_realized_pnl_eur='-70')['reasons']


@pytest.mark.parametrize('change,reason', [
    ({'available_capital_eur': '399.99'}, 'insufficient_available_capital'),
    ({'proposed_capital_eur': '500.01'}, 'allocation_limit'),
    ({'active_positions': 3}, 'position_limit'),
])
def test_available_cash_allocation_and_position_constraints(change, reason):
    assert reason in risk(**change)['reasons']


@pytest.mark.parametrize('changes', [
    {'reserved_risk_eur': None}, {'risk_estimate_complete': False},
    {'state_day': '2026-11-15'}, {'daily_halt_latched': None},
])
def test_missing_costs_or_stale_daily_state_never_become_zero_risk(changes):
    out = risk(**changes)
    assert out['status'] == 'unknown' and not out['trade_authorized']


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', True, -1, 0, 0.1])
def test_invalid_proposed_risk_is_rejected(bad):
    with pytest.raises(ValueError):
        risk(proposed_risk_eur=bad)


def test_day_is_dublin_local_date_and_does_not_release_carried_reservations():
    summer = datetime(2026, 6, 1, 23, 30, tzinfo=UTC)
    assert risk(as_of=summer, state_day='2026-06-01')['status'] == 'unknown'
    out = risk(as_of=summer, state_day='2026-06-02', reserved_risk_eur='40',
               proposed_risk_eur='1', active_positions=2)
    assert out['reasons'] == ['combined_open_risk_limit']


@pytest.mark.parametrize('delay', [60, 180, 300])
def test_declared_reaction_scenarios_need_a_fresh_post_response_quote(delay):
    out = timing(delay)
    assert out['status'] == 'profile_checks_passed'
    assert out['ready_at'] == (NOW + timedelta(seconds=delay)).isoformat()
    assert not out['trade_authorized']


def test_four_minute_setup_passes_one_and_three_but_not_five_minutes():
    expiry = NOW + timedelta(minutes=4)
    assert timing(60, expires_at=expiry)['status'] == 'profile_checks_passed'
    assert timing(180, expires_at=expiry)['status'] == 'profile_checks_passed'
    out = timing(300, expires_at=expiry)
    assert out['status'] == 'blocked'
    assert 'response_exceeds_entry_window' in out['reasons']
    assert 'entry_window_expired' in out['reasons']


def test_exact_expiry_is_too_late_and_does_not_extend_the_plan():
    out = timing(60, expires_at=NOW + timedelta(seconds=60))
    assert 'entry_window_expired' in out['reasons']
    assert out['entry_deadline'] == (NOW + timedelta(seconds=60)).isoformat()


def test_quote_before_response_is_not_reused_and_delay_is_not_quote_freshness():
    out = timing(300, quote_observed_at=NOW + timedelta(seconds=290))
    assert out['reasons'] == ['quote_predates_manual_readiness']
    out = timing(300, quote_observed_at=NOW + timedelta(seconds=100))
    assert 'stale_quote' in out['reasons']


def test_late_decision_cannot_backdate_readiness():
    out = timing(60, as_of=NOW + timedelta(seconds=220),
                 decision_available_at=NOW + timedelta(seconds=210),
                 quote_observed_at=NOW + timedelta(seconds=200),
                 quote_received_at=NOW + timedelta(seconds=220))
    assert out['ready_at'] == (NOW + timedelta(seconds=210)).isoformat()
    assert out['reasons'] == ['quote_predates_manual_readiness']


@pytest.mark.parametrize('field', ['alert_received_at', 'decision_available_at',
                                   'quote_received_at', 'session_permitted'])
def test_absent_delivery_or_other_evidence_is_unknown(field):
    assert timing(**{field: None})['status'] == 'unknown'


def test_future_or_inverted_quote_clocks_are_not_usable_evidence():
    assert timing(quote_received_at=NOW + timedelta(seconds=90))['status'] == 'unknown'
    assert timing(quote_observed_at=NOW + timedelta(seconds=61))['status'] == 'unknown'


def test_session_and_exit_window_still_apply_to_all_day_availability():
    assert 'session_not_permitted' in timing(session_permitted=False)['reasons']
    out = timing(exit_by=NOW + timedelta(seconds=90))
    assert 'entry_window_expired' in out['reasons']
    assert out['entry_deadline'] == (NOW + timedelta(seconds=60)).isoformat()


def test_dublin_summer_cutoff_weekend_and_overnight_entries_are_blocked():
    summer = datetime(2026, 6, 1, 21, tzinfo=UTC)
    out = timing(as_of=summer, alert_received_at=summer-timedelta(seconds=60),
                 decision_available_at=summer-timedelta(seconds=60),
                 quote_observed_at=summer, quote_received_at=summer,
                 expires_at=summer+timedelta(minutes=5), exit_by=summer+timedelta(minutes=30))
    assert 'dublin_entry_cutoff' in out['reasons']
    saturday = NOW + timedelta(days=5)
    out = timing(as_of=saturday, alert_received_at=saturday-timedelta(seconds=60),
                 decision_available_at=saturday-timedelta(seconds=60),
                 quote_observed_at=saturday, quote_received_at=saturday,
                 expires_at=saturday+timedelta(minutes=5), exit_by=saturday+timedelta(hours=1))
    assert 'weekend' in out['reasons']
    assert 'not_same_day_intraday_setup' in timing(exit_by=NOW+timedelta(days=1))['reasons']


@pytest.mark.parametrize('delay', [0, 59, 120, 301, True])
def test_undeclared_delay_or_naive_timestamp_fails_closed(delay):
    with pytest.raises(ValueError, match='undeclared_response_scenario'):
        timing(delay)
    with pytest.raises(ValueError, match='timezone_required'):
        timing(as_of=NOW.replace(tzinfo=None))
