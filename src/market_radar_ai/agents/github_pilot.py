"""GitHub storage check by default; single paid connectivity request only on opt-in."""
from datetime import datetime, timezone
import json
import os
from .github_budget import GitHubBudgetStore, GitHubSpendingLedger, REPOSITORY
from .openai_pilot import OpenAIPilot


def storage_check(store, now):
    ledger=GitHubSpendingLedger(store)
    state,_=store.load()
    identity='storage-check-v1'
    if identity not in state['entries']:
        ledger.reserve(identity,1,now)
    # This fixed identity is a storage-only marker: it never invokes a provider.
    ledger.settle(identity,0)
    return GitHubSpendingLedger(store).summary()


def connectivity_check(store, *, key, now, fx_provider=None):
    state,_=store.load()
    identity='openai-connectivity-v1'
    if identity in state['entries']:
        # A settled charge alone does not prove a valid model response.
        return {'status':'already_attempted_no_retry', 'budget':GitHubSpendingLedger(store).summary()}
    if not key:
        raise ValueError('OPENAI_API_KEY is missing')
    if fx_provider is None:
        from ..market_data.providers.fx import YahooFxProvider
        fx_provider=YahooFxProvider()
    fx=fx_provider.fetch('USD',now=now)
    ledger=GitHubSpendingLedger(store)
    pilot=OpenAIPilot(api_key=key,ledger=ledger,eur_per_usd=fx.eur_per_unit,enabled=True)
    result=pilot.call(prompt='Connectivity check only. Return {"ok":true}.',
        schema={'type':'object','properties':{'ok':{'type':'boolean','const':True}}},
        request_id=identity,now=now,max_output_tokens=64)
    return {'status':'connected','input_tokens':result.input_tokens,'output_tokens':result.output_tokens,
            'cost_usd':str(result.cost_usd),'estimated_cost_microeur':result.estimated_cost_microeur,
            'eur_per_usd':str(result.eur_per_usd),'fx_observed_at':fx.observed_at.isoformat(),
            'fx_source':fx.source,'budget':ledger.summary()}


def main():
    if (os.environ.get('GITHUB_REPOSITORY') != REPOSITORY
            or os.environ.get('GITHUB_REF') != 'refs/heads/phase-1/market-data-layer'
            or os.environ.get('GITHUB_EVENT_NAME') not in {'push','workflow_dispatch'}):
        raise SystemExit('Pilot restricted to the development branch of market-radar-ai')
    try:
        store=GitHubBudgetStore(os.environ.get('GH_BUDGET_TOKEN',''))
        now=datetime.now(timezone.utc)
        if os.environ.get('RUN_OPENAI_CONNECTIVITY') == 'enabled':
            result=connectivity_check(store,key=os.environ.get('OPENAI_API_KEY',''),now=now)
        else:
            result={'status':'storage_verified_no_paid_call','budget':storage_check(store,now)}
        print(json.dumps(result,sort_keys=True))
        summary=os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary,'a') as file:
                file.write('### AI pilot status\n\n```json\n'+json.dumps(result,indent=2)+'\n```\n')
    except Exception:
        raise SystemExit('Pilot stopped. Inspect the durable budget record; no automatic retry was made.') from None


if __name__ == '__main__':
    main()
