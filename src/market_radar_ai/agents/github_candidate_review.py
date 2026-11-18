"""One shortlisted candidate per manual run; dry-run default, no notifications."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .candidate_packages import build_packages
from .candidate_review import run_paid, reproduce
from .github_budget import GitHubBudgetStore, GitHubSpendingLedger, REPOSITORY
from .openai_pilot import OpenAIPilot
from ..market_data.providers.fx import YahooFxProvider


def execute(capture, feed, root, *, env, clock=lambda: datetime.now(timezone.utc)):
    if (env.get('GITHUB_REPOSITORY') != REPOSITORY
            or env.get('GITHUB_REF') != 'refs/heads/phase-1/market-data-layer'
            or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_RUN_ATTEMPT') != '1'):
        raise ValueError('first_manual_attempt_required')
    mode = env.get('CANDIDATE_REVIEW_MODE', 'dry_run')
    market = env.get('CANDIDATE_MARKET', 'auto')
    scope = env.get('REVIEW_SCOPE', 'candidate')
    if mode not in ('dry_run', 'paid') or market not in ('auto', 'stocks', 'crypto'):
        raise ValueError('invalid_candidate_review_mode')
    if scope not in ('candidate', 'context') or (scope=='context' and market=='crypto'):
        raise ValueError('invalid_research_scope')
    if scope=='context' and env.get('SEND_CANDIDATE_REVIEW')=='true':
        raise ValueError('context_archive_contract_not_connected')
    root = Path(root)
    if root.exists():
        raise ValueError('preserve_existing_artifacts')
    root.mkdir(parents=True)
    status = {'mode': mode, 'state': 'preparing', 'model_calls': 0, 'trade_authorized': False}
    ledger = None

    def save(name, value):
        (root/name).write_text(json.dumps(value, indent=2)+'\n')

    try:
        if scope=='context':
            from .context_packages import build_context_packages
            batch = build_context_packages(capture, feed, now=clock())
            status['research_scope'] = 'context'
        else:
            batch = build_packages(capture, feed, now=clock())
        choices = [r for r in batch['packages'] if market == 'auto' or r['package']['market'] == market]
        if not choices:
            status['state'] = 'no_reviewable_candidate'
        else:
            # Stable quota/ranking order; no hardcoded ticker and no paid batch fanout.
            record = choices[0]
            save('package.json', record)
            status.update(candidate_id=record['package']['candidate_id'], package_id=record['package_id'],
                          state='ready_dry_run')
            if mode == 'paid':
                key = env.get('OPENAI_API_KEY', '')
                token = env.get('GH_BUDGET_TOKEN', '')
                if not key or not token:
                    raise ValueError('missing_credentials')
                # Cost conversion only: does not clear the candidate's trading FX gap.
                fx = YahooFxProvider().fetch('USD', now=clock())
                save('cost-fx.json', fx.model_dump(mode='json'))
                ledger = GitHubSpendingLedger(GitHubBudgetStore(token))
                save('budget-before.json', ledger.summary())
                reproduce(record, capture, feed, now=clock())
                client = OpenAIPilot(api_key=key, ledger=ledger, eur_per_usd=fx.eur_per_unit,
                                     enabled=True, count_input_tokens=True)
                audit = run_paid(client, record, capture, feed, path=root/'review.json', clock=clock, enabled=True)
                status.update(state=audit['state'], model_calls=len(audit['calls']))
                save('result.json', audit['result'])
                from ..dashboard.candidate_delivery import export_archive, deliver
                if scope=='candidate':
                    save('dashboard-archive.json', export_archive(record, capture, feed, audit))
                else:
                    status['dashboard_delivery_state'] = 'context_archive_not_connected'
                if scope=='candidate' and env.get('SEND_CANDIDATE_REVIEW') == 'true':
                    try:
                        delivery = deliver(record, capture, feed, audit, env=env, clock=clock)
                    except Exception:
                        delivery = {'state':'blocked_or_unconfirmed','retry_allowed':False,
                                    'trade_authorized':False}
                    save('dashboard-delivery.json', delivery)
                    status['dashboard_delivery_state'] = delivery['state']
    except Exception:
        status.update(state='blocked_or_failed', reason='Inspect artifacts and shared budget; no automatic retry')
        if mode == 'paid':
            status['model_calls'] = None  # a failed call may still have reserved or spent money
        raise RuntimeError('Candidate review blocked or failed; inspect saved artifacts') from None
    finally:
        save('status.json', status)
        if ledger is not None:
            try:
                save('budget-after.json', ledger.summary())
            except Exception:
                save('budget-after.json', {'state': 'unavailable', 'reconciliation_required': True})
    return status


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
