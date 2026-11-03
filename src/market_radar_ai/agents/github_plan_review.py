"""Fresh paper-plan review runner; dry-run default, manual opt-in paid mode."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from .plan_review import prepare, run_paid
from .alpaca_paper_rehearsal import build
from .github_budget import GitHubBudgetStore, GitHubSpendingLedger, REPOSITORY
from .openai_pilot import OpenAIPilot
from ..market_data.broker_check import check
from ..market_data.alpaca_check import capture
from ..market_data.session_calendar import capture_calendar
from ..market_data.providers.fx import YahooFxProvider


def mode_for(env):
    if env.get('GITHUB_REPOSITORY')!=REPOSITORY or env.get('GITHUB_REF')!='refs/heads/phase-1/market-data-layer':
        raise ValueError('wrong_repository_or_branch')
    mode=env.get('PLAN_REVIEW_MODE','dry_run')
    if mode not in ('dry_run','paid'): raise ValueError('invalid_mode')
    if mode=='paid' and (env.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
                        or env.get('GITHUB_RUN_ATTEMPT')!='1'):
        raise ValueError('paid_requires_first_manual_attempt')
    return mode


def execute(root, *, env, clock=lambda:datetime.now(timezone.utc)):
    mode=mode_for(env)
    root=Path(root)
    if root.exists(): raise ValueError('preserve_existing_artifacts')
    root.mkdir(parents=True)
    def save(name,value):
        (root/name).write_text(json.dumps(value,indent=2)+'\n')
    status=dict(mode=mode,state='preparing',trade_authorized=False,model_calls=0)
    ledger=None
    try:
        save('status.json',status)
        # Slow catalogue first; no market evidence ages while it loads.
        cat=check();save('catalogue.json',cat)
        calendar=capture_calendar();save('calendar.json',calendar)
        market=capture()
        if calendar is not None:market['calendar']=calendar
        save('capture.json',market)
        fx=YahooFxProvider().fetch('USD');save('fx.json',fx.model_dump(mode='json'))
        draft=build(market,cat,fx,now=clock())
        draft['fx_evidence']=fx.model_dump(mode='json');save('draft.json',draft)
        if draft['state']!='conditional_paper_draft':
            status.update(state='no_reviewable_plan',failures=draft['failures'])
        else:
            packet=prepare(market,cat,draft)
            (root/'packet.json').write_text(packet+'\n')
            if mode=='dry_run': status['state']='ready_dry_run'
            else:
                key=env.get('OPENAI_API_KEY','');token=env.get('GH_BUDGET_TOKEN','')
                if not key or not token: raise ValueError('missing_credentials')
                ledger=GitHubSpendingLedger(GitHubBudgetStore(token))
                save('budget-before.json',ledger.summary())
                client=OpenAIPilot(api_key=key,ledger=ledger,eur_per_usd=fx.eur_per_unit,enabled=True,count_input_tokens=True)
                result=run_paid(client,packet,path=root/'review.json',clock=clock,enabled=True)
                from ..dashboard.plan_review import export_review
                exported=export_review(market,cat,draft,result,now=clock())
                save('dashboard-review.json',exported)
                from ..dashboard.notification import render_review
                save('notification-preview.json',render_review(exported,now=clock()))
                status.update(state=result['state'],model_calls=len(result['calls']))
                if env.get('SEND_FRESH_REVIEW') == 'true':
                    from ..dashboard.fresh_notification import deliver
                    from ..dashboard.delivery_ledger import DeliveryLedger, GitHubDeliveryStore
                    try:
                        delivery = deliver(market, cat, draft, result, env=env,
                            ledger=DeliveryLedger(GitHubDeliveryStore(token)), clock=clock)
                    except Exception:
                        # Review completion and spending remain true even when
                        # the optional notification fails. Never rerun the AI.
                        delivery = {'state':'blocked_or_unconfirmed',
                                    'retry_allowed':False, 'trade_authorized':False}
                    save('notification-delivery.json', delivery)
                    status['notification_state'] = delivery['state']
    except Exception:
        status.update(state='blocked_or_failed',reason='Inspect saved artifacts and budget; no automatic retry')
        # A failed request may have reserved/spent money. Never label it zero-cost.
        if mode=='paid':status['model_calls']=None
        raise RuntimeError('Plan review stopped; inspect saved evidence') from None
    finally:
        save('status.json',status)
        if ledger is not None:
            try:save('budget-after.json',ledger.summary())
            except Exception:save('budget-after.json',{'state':'unavailable','reconciliation_required':True})
    return status


if __name__=='__main__':
    try:print(json.dumps(execute('artifacts/plan-review',env=os.environ)))
    except Exception:raise SystemExit('Plan review blocked or failed; inspect artifacts') from None
