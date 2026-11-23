"""Cost and time-headroom diagnostics on original packets; never admission."""
from collections import Counter
from datetime import timedelta

from .candidate_packages import digest
from .execution_research import PROTOCOL as COST_PROTOCOL, size, money
from .paper_comparison import aware, validate_packet


POLICY = {
    'version':'manual-plan-preflight-v1', 'cost_profile':'eur_conversion',
    'owner_currency_route_confirmed_on':'2026-11-23',
    'cost_basis':'existing_execution_research_worst_allowed_entry_and_frozen_fee_assumptions',
    'cost_fields':{k:COST_PROTOCOL[k] for k in ('profiles','sec_sale_rate','finra_usd_per_share',
        'fee_rounding','fee_schedule_checked','fee_schedule_expires','minimum_net_rr',
        'maximum_allocation_eur','maximum_trade_risk_eur','maximum_entry_gap_bps',
        'maximum_spread_bps','exit_window_seconds')},
    'response_seconds':[60,180,300], 'actual_notification_required':True,
    'scope':'original_packets_before_review_not_final_watches_or_fills',
    'automatic_admission':False, 'trade_authorized':False,
}
POLICY_ID = digest(POLICY)


def assess_packets(packets, *, source_at, processed_at):
    source_at, processed_at = aware(source_at), aware(processed_at)
    if source_at > processed_at:
        raise ValueError('preflight_source_from_future')
    rows, seen = [], set()
    for packet in packets:
        body = validate_packet(packet, source_at)
        if packet['packet_id'] in seen or aware(body['assembled_at']) != source_at:
            raise ValueError('preflight_duplicate_or_mixed_capture')
        seen.add(packet['packet_id'])
        plan = body['plan']
        deadline = min(aware(plan['expires_at']), aware(plan['exit_by'])-
                       timedelta(seconds=COST_PROTOCOL['exit_window_seconds']))
        row = {'packet_id':packet['packet_id'], 'candidate_id':body['candidate_id'],
            'original_expiry':plan['expires_at'], 'source_qualified_at':source_at.isoformat(),
            'cost_status':'unavailable', 'cost_reasons':[], 'costs_verified':False,
            'notification_acknowledged_at':None, 'response_eligibility':'unknown_without_notification_and_fresh_quote',
            'latest_possible_ack_by_delay':{str(delay):(deadline-timedelta(seconds=delay)).isoformat()
                for delay in POLICY['response_seconds']},
            'original_plan_headroom_seconds':max(0,(deadline-source_at).total_seconds())}
        if not body['candidate_id'].startswith('stocks:') or plan['native_currency'] != 'USD':
            row['cost_reasons'].append('cost_model_unavailable_for_market')
        elif not COST_PROTOCOL['fee_schedule_checked'] <= source_at.date().isoformat() < COST_PROTOCOL['fee_schedule_expires']:
            row['cost_reasons'].append('fee_schedule_stale_at_source')
        else:
            estimate = size(POLICY['cost_profile'], plan)
            row.update(cost_status='assessed', quantity=money(estimate['quantity']),
                estimated_net_rr=money(estimate['rr']), estimated_reward_eur=money(estimate['reward']),
                estimated_risk_eur=money(estimate['risk']), estimated_capital_eur=money(estimate['capital']),
                estimated_target_fees_eur={k:money(v) for k,v in estimate['target_fees'].items()},
                estimated_stop_fees_eur={k:money(v) for k,v in estimate['stop_fees'].items()},
                estimated_slippage_to_target_eur=money(estimate['slippage_to_target_eur']))
            if estimate['rr'] < 2:
                row['cost_status']='blocked_under_assumptions'
                row['cost_reasons'].append('scenario_net_reward_below_2r')
            else:
                row['cost_status']='cost_check_passed_under_assumptions'
        rows.append(row)
    return {'schema_version':'manual-plan-preflight-v1', 'policy_id':POLICY_ID, 'policy':POLICY,
        'as_of':processed_at.isoformat(), 'source_qualified_at':source_at.isoformat(),
        'source_packets_sha256':digest(packets), 'cost_profile':POLICY['cost_profile'],
        'costs_verified':False, 'packet_count':len(rows),
        'cost_status_counts':dict(Counter(r['cost_status'] for r in rows)),
        'cost_reason_counts':dict(Counter(b for r in rows for b in r['cost_reasons'])),
        'rows':rows, 'model_calls':0, 'trade_authorized':False, 'ordinary_alerts_changed':False,
        'note':'Cost-only diagnostic, no portfolio or fill simulation. No actual acknowledgement exists '
               'for these original packets. Final revalidated watch deadlines can differ. '
               'Cash, risk, notification, quotes and observed outcomes still require their existing checks.'}
