"""Per-run paper-session accounting. Never upgrades research into trade approval."""
from datetime import datetime
from decimal import Decimal, InvalidOperation


def build_session_report(status, draft, review, *, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    # Only accept the runner's validated dashboard export as review evidence.
    reviewed = (isinstance(review, dict)
        and review.get('schema_version') == 'paper-review-dashboard-v1'
        and review.get('review_status') == 'COMPLETED_UNAPPROVED'
        and review.get('trade_authorized') is False
        and isinstance(review.get('reviews'), list) and len(review['reviews']) == 8)
    draft = draft if isinstance(draft, dict) else {}
    plan = draft.get('plan') if isinstance(draft.get('plan'), dict) else None
    fresh = False
    risk_ok = False
    if plan:
        try:
            expiry = datetime.fromisoformat(plan['expires_at'])
            fresh = expiry.tzinfo is not None and now < expiry
            loss = Decimal(plan['planned_loss_eur'])
            risk_ok = loss.is_finite() and 0 < loss <= 20
        except (KeyError, TypeError, ValueError, InvalidOperation):
            pass
    blockers = list(draft.get('blockers', []))
    failures = list(draft.get('failures', []))
    # Review execution resolves only whether a review ran, not its input evidence gaps.
    if reviewed:
        blockers = [b for b in blockers if b != 'six_agent_plan_review_not_run']
    reasons = failures + blockers
    if not plan: reasons.append('no_conditional_plan')
    if plan and not fresh: reasons.append('plan_expired_or_invalid_expiry')
    if plan and not risk_ok: reasons.append('planned_loss_invalid_or_over_limit')
    if not reviewed: reasons.append('validated_eight_stage_review_unavailable')
    reasons.append('research_pipeline_does_not_authorize_trades')
    return {
        'schema_version': 'paper-session-report-v1', 'evaluated_at': now.isoformat(),
        'runner_state': status.get('state', 'unknown'),
        'session_result': 'REVIEWED_NO_TRADE' if reviewed else 'UNREVIEWED_NO_TRADE',
        'trade_authorized': False, 'paper_position_opened': False,
        'validated_review_completed': reviewed,
        'review_snapshot_id': review.get('snapshot_id') if reviewed else None,
        'review_verdict': review.get('final_verdict') if reviewed else None,
        'checks': {'conditional_plan_present': plan is not None,
                   'plan_unexpired': fresh, 'planned_loss_within_eur20': risk_ok,
                   'broker_account_eligibility_verified': False,
                   'executable_prices_and_costs_verified': False,
                   'independent_catalyst_review_verified': False},
        'blocking_reasons': sorted(set(reasons)),
        'outcome': {'status': 'NOT_OPENED', 'net_pnl_eur': None,
                    'accuracy_score': None, 'reason': 'No admitted paper trade; do not count as a win or loss'},
        'scope': 'Single NVDA candidate review; not a complete market-wide paper session',
    }
