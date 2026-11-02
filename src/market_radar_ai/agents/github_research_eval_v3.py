"""One-shot v3 evaluation. Uses the shared EUR 0.50 pilot allowance."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from .github_budget import GitHubBudgetStore,GitHubSpendingLedger,REPOSITORY
from .openai_pilot import OpenAIPilot
from .research_eval_v3 import run,VERSION
from ..market_data.providers.fx import YahooFxProvider


def main():
    if (os.environ.get('RUN_RESEARCH_EVAL_V3')!='enabled'
        or os.environ.get('GITHUB_REPOSITORY')!=REPOSITORY
        or os.environ.get('GITHUB_REF')!='refs/heads/phase-1/market-data-layer'
        or os.environ.get('GITHUB_EVENT_NAME')!='push'):
        raise SystemExit('V3 evaluation disabled')
    path=Path('artifacts/research-eval-v3/result.json')
    try:
        store=GitHubBudgetStore(os.environ.get('GH_BUDGET_TOKEN',''))
        state,_=store.load()
        prefix={k:v for k,v in state['entries'].items() if k.startswith(VERSION+':')}
        prior=None
        if prefix:
            prior=json.loads(Path('docs/evaluations/research-eval-v3-checkpoint.json').read_text())
            saved={c['request_id']:c for c in prior['calls']+prior.get('rejected_calls',[])}
            if set(prefix)!=set(saved): raise RuntimeError('Unreconciled V3 attempts')
            for identity,row in prefix.items():
                if (row['actual'] is None or row['actual']!=saved[identity]['estimated_cost_microeur']
                    or row['usage'] is None or row['usage']['response_id']!=saved[identity]['response_id']
                    or row['usage']['cost_usd']!=saved[identity]['cost_usd']
                    or row['usage']['model']!=prior['model']):
                    raise RuntimeError('Unreconciled V3 cost')
        key=os.environ.get('OPENAI_API_KEY','')
        if not key: raise ValueError('API key missing')
        now=datetime.now(timezone.utc);fx=YahooFxProvider().fetch('USD',now=now)
        client=OpenAIPilot(api_key=key,ledger=GitHubSpendingLedger(store),eur_per_usd=fx.eur_per_unit,enabled=True)
        report=run(client,now=now,path=path,prior_report=prior)
        report['budget']=client.ledger.summary()
        report['fx']={'eur_per_usd':str(fx.eur_per_unit),'observed_at':fx.observed_at.isoformat(),'source':fx.source}
        path.write_text(json.dumps(report,indent=2)+'\n')
        print('EVALUATION_V3_RESULT='+json.dumps(report))
        if not all(report['checks'].values()): raise RuntimeError('Quality checks failed')
    except Exception:
        if path.exists(): print('EVALUATION_V3_PARTIAL='+path.read_text().replace('\n',''))
        raise SystemExit('V3 stopped. Inspect saved report and budget before further requests.') from None


if __name__=='__main__': main()
