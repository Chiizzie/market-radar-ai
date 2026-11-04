"""Bounded weekday six-role research decisions, separate from collection/orders."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .candidate_packages import build_packages
from .session_briefing import build_briefing
from .candidate_review import run_paid, reproduce
from .github_budget import GitHubBudgetStore, GitHubSpendingLedger, validate_state, REPOSITORY
from .openai_pilot import OpenAIPilot
from ..market_data.providers.fx import YahooFxProvider
from ..dashboard.candidate_delivery import export_archive, deliver

WORKFLOW_REF = REPOSITORY + '/.github/workflows/scheduled-scanner.yml@refs/heads/main'
PREFIX = 'scheduled-research-v1:'


def permitted(env, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    local = now.astimezone(ZoneInfo('Europe/Dublin'))
    return (env.get('GITHUB_REPOSITORY') == REPOSITORY
            and env.get('GITHUB_REF') == 'refs/heads/main'
            and env.get('GITHUB_WORKFLOW_REF') == WORKFLOW_REF
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_RUN_ATTEMPT') == '1'
            and env.get('SCANNER_VERIFY_OUTSIDE_WINDOW') != 'true'
            and env.get('SCHEDULED_REVIEW_MODE') == 'paid'
            and local.weekday() < 5 and 8 <= local.hour < 22)


def quota_bucket(record):
    p = record['package']
    return 'stocks_'+p['review_slot'] if p['schema_version']=='session-evidence-package-v1' else p['market']


def opening_recovery_allowed(state, day):
    opening = state['entries'].get(PREFIX+day+':stocks_opening')
    return (opening is not None and opening['actual'] == 0
            and not any(k.startswith('session-review-v1:') and e['day'] == day
                        for k, e in state['entries'].items()))


def authorized_recovery_bucket(record, env, now):
    """Explicit dated authorization for one fresh attempt, never a ledger reset."""
    day = now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
    if (permitted(env, now) and env.get('SCHEDULED_RECOVERY_DATE') == day
            and record['package'].get('review_slot') == 'intraday'
            and record['package'].get('schema_version') == 'session-evidence-package-v1'):
        return 'stocks_verified_recovery'
    return quota_bucket(record)


def claim_review(store, market, now):
    """One durable attempt per market/day, including failures and lost replies.

    The CAS marker costs one micro-euro of held budget until its zero-cost
    settlement. A concurrent/lost write never allows generation to start.
    """
    if market not in ('stocks', 'crypto', 'stocks_morning', 'stocks_preopen', 'stocks_opening', 'stocks_intraday', 'stocks_verified_recovery'):
        raise ValueError('invalid_market')
    state, _ = store.load()
    validate_state(state)
    day = now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
    key = PREFIX + day + ':' + market
    if key in state['entries']:
        return False
    # Reserve headroom for the complete bounded review; per-call reservations
    # still enforce the actual hard caps. Do not begin near exhaustion.
    for period, cap in state['limits_microeur'].items():
        entries = [e for e in state['entries'].values() if period == 'lifetime'
                   or (period == 'daily' and e['day'] == day)
                   or (period == 'monthly' and e['day'][:7] == day[:7])]
        if cap - sum(e['reserved'] if e['actual'] is None else e['actual'] for e in entries) < 150000:
            return False
    ledger = GitHubSpendingLedger(store)
    ledger.reserve(key, 1, now)
    ledger.settle(key, 0)
    return True


def decision_summary(record, capture, feed, audit):
    # Validate all eight responses, identities, citations, timing and accounting
    # by reproducing the existing archive contract before deriving a decision.
    archive = export_archive(record, capture, feed, audit)
    result = audit['result']
    reviews = result['reviews']
    rejected = any(r['verdict'] == 'REJECT' for r in reviews)
    follow = (not rejected and reviews[-1]['verdict'] == 'RESEARCH_WORTH_FOLLOWING')
    gaps = [x for x in result['missing_evidence'] if x != 'six_agent_review_not_run']
    if result['evidence_status'] not in ('CURRENT_RESEARCH_DATA', 'CURRENT_CONTEXT_ONLY'):
        gaps.append('review_evidence_expired')
    return dict(schema_version='scheduled-research-decision-v1',
                candidate_id=result['candidate_id'], package_id=result['package_id'],
                completed_at=result['completed_at'], review_origin='PAID_AI',
                research_verdict='REJECT' if rejected else 'WATCHLIST' if follow else 'MORE_EVIDENCE_REQUIRED',
                final_decision='NO_ACTION', trade_authorized=False, paper_only=True,
                plan=record['package'].get('plan'), blockers=list(dict.fromkeys(gaps)),
                reason='Research review completed; no approved EUR trade plan or execution admission supplied.',
                estimated_cost_microeur=archive['estimated_cost_microeur'],
                model_calls=8, evidence_status=result['evidence_status'],
                research_mode=record['package'].get('research_mode'),
                symbol_decisions=reviews[-1].get('symbol_decisions', []))


def execute(capture, feed, root, *, env, clock=lambda: datetime.now(timezone.utc)):
    root = Path(root)
    if root.exists():
        raise ValueError('preserve_existing_artifacts')
    root.mkdir(parents=True)
    status = dict(state='not_started', model_calls=0, trade_authorized=False)
    def save(name, value):
        (root/name).write_text(json.dumps(value, indent=2)+'\n')
    ledger = None
    try:
        if not permitted(env, clock()):
            status['state'] = 'outside_review_scope_or_window'
            return status
        briefing = build_briefing(capture, feed, now=clock())
        batch = build_packages(capture, feed, now=clock())
        batch['packages'] = briefing['packages'] + batch['packages']
        if not batch['packages']:
            status['state'] = 'no_reviewable_candidate'
            return status
        key, token = env.get('OPENAI_API_KEY'), env.get('GH_BUDGET_TOKEN')
        if not key or not token:
            raise ValueError('missing_review_credentials')
        store = GitHubBudgetStore(token)
        ledger = GitHubSpendingLedger(store)
        save('budget-before.json', ledger.summary())
        state, _ = store.load()
        day = clock().astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
        # Catch up only a failed opening attempt that never reserved a model call.
        # Retain the original marker; claim a separate single recovery slot.
        safe_recovery = opening_recovery_allowed(state, day)
        batch['packages'] = [r for r in batch['packages']
            if r['package'].get('review_slot') != 'intraday' or safe_recovery
            or authorized_recovery_bucket(r, env, clock()) == 'stocks_verified_recovery']
        choices = [r for r in batch['packages']
                   if PREFIX+day+':'+authorized_recovery_bucket(r, env, clock()) not in state['entries']]
        if not choices:
            status['state'] = 'daily_review_quota_reached'
            return status
        record = choices[0]  # existing stable shortlist: stocks before crypto
        fx = YahooFxProvider().fetch('USD', now=clock())
        save('cost-fx.json', fx.model_dump(mode='json'))
        from copy import deepcopy
        capture = deepcopy(capture)
        capture['paper_scenarios_enabled'] = True
        capture['paper_plan_fx'] = fx.model_dump(mode='json')
        refreshed = (build_briefing if record['package']['schema_version']=='session-evidence-package-v1'
                     else build_packages)(capture, feed, now=clock())
        matches = [r for r in refreshed['packages']
                   if r['package']['candidate_id'] == record['package']['candidate_id']]
        if not matches:
            status['state'] = 'candidate_expired_during_preparation'
            return status
        record = matches[0]
        save('decision-capture.json', capture)
        save('package.json', record)
        reproduce(record, capture, feed, now=clock())
        if not permitted(env, clock()):
            status['state'] = 'outside_review_scope_or_window'
            return status
        if not claim_review(store, authorized_recovery_bucket(record, env, clock()), clock()):
            status['state'] = 'quota_or_budget_deferred'
            return status
        client = OpenAIPilot(api_key=key, ledger=ledger, eur_per_usd=fx.eur_per_unit,
                             enabled=True, count_input_tokens=True)
        status.update(state='reviewing', model_calls=None, candidate_id=record['package']['candidate_id'])
        save('status.json', status)
        audit = run_paid(client, record, capture, feed, path=root/'review.json', clock=clock, enabled=True)
        summary = decision_summary(record, capture, feed, audit)
        save('decision.json', summary)
        save('dashboard-archive.json', export_archive(record, capture, feed, audit))
        status.update(state='decision_completed', model_calls=8, final_decision=summary['final_decision'],
                      research_verdict=summary['research_verdict'])
        # Delivery failure must not cause another paid review on the next tick.
        from ..dashboard.scheduled_notification import deliver as notify
        delivery_failures = []
        for channel, sender in [('dashboard', deliver), ('telegram', notify)]:
            try:
                receipt = sender(record, capture, feed, audit, env=env, clock=clock)
                save(channel+'-delivery.json', receipt)
                status[channel+'_delivery_state'] = receipt['state']
            except Exception:
                save(channel+'-delivery.json', {'state':'unconfirmed_do_not_retry'})
                status[channel+'_delivery_state'] = 'unconfirmed_do_not_retry'
                delivery_failures.append(channel)
        if delivery_failures:
            raise RuntimeError('Research delivery incomplete; do not replay paid review')
        return status
    except Exception:
        status['state'] = 'blocked_or_failed'
        raise RuntimeError('Scheduled review stopped; inspect artifacts and durable budget, never replay paid calls') from None
    finally:
        save('status.json', status)
        if ledger is not None:
            try:
                save('budget-after.json', ledger.summary())
            except Exception:
                save('budget-after.json', {'state':'unavailable','reconciliation_required':True})


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.capture.stat().st_size > 4_000_000 or args.evidence.stat().st_size > 2_000_000:
        raise ValueError('input_too_large')
    print(json.dumps(execute(json.loads(args.capture.read_text()), json.loads(args.evidence.read_text()),
                            args.output, env=os.environ)))


if __name__ == '__main__':
    main()
