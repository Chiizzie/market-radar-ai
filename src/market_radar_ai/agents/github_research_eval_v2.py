"""One-shot v2 evaluation. Uses the shared EUR 0.50 pilot allowance."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from .github_budget import GitHubBudgetStore,GitHubSpendingLedger,REPOSITORY
from .openai_pilot import OpenAIPilot
from .research_eval_v2 import run,VERSION
from ..market_data.providers.fx import YahooFxProvider


def main():
    if (os.environ.get('RUN_RESEARCH_EVAL_V2')!='enabled'
        or os.environ.get('GITHUB_REPOSITORY')!=REPOSITORY
        or os.environ.get('GITHUB_REF')!='refs/heads/phase-1/market-data-layer'
        or os.environ.get('GITHUB_EVENT_NAME')!='push'):
        raise SystemExit('V2 evaluation disabled')
    path=Path('artifacts/research-eval-v2/result.json')
    try:
        store=GitHubBudgetStore(os.environ.get('GH_BUDGET_TOKEN',''))
        state,_=store.load()
        if any(k.startswith(VERSION+':') for k in state['entries']):
            raise RuntimeError('V2 already attempted; inspect before retry')
        key=os.environ.get('OPENAI_API_KEY','')
        if not key: raise ValueError('API key missing')
        now=datetime.now(timezone.utc);fx=YahooFxProvider().fetch('USD',now=now)
        client=OpenAIPilot(api_key=key,ledger=GitHubSpendingLedger(store),eur_per_usd=fx.eur_per_unit,enabled=True)
        report=run(client,now=now,path=path)
        report['budget']=client.ledger.summary()
        report['fx']={'eur_per_usd':str(fx.eur_per_unit),'observed_at':fx.observed_at.isoformat(),'source':fx.source}
        path.write_text(json.dumps(report,indent=2)+'\n')
        print('EVALUATION_V2_RESULT='+json.dumps(report))
        if not all(report['checks'].values()): raise RuntimeError('Quality checks failed')
    except Exception:
        if path.exists(): print('EVALUATION_V2_PARTIAL='+path.read_text().replace('\n',''))
        raise SystemExit('V2 stopped. Inspect saved report and budget before further requests.') from None


if __name__=='__main__': main()
