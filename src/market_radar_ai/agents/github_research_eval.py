"""One-shot evaluation runner using the existing persistent pilot budget."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from .github_budget import GitHubBudgetStore,GitHubSpendingLedger,REPOSITORY
from .openai_pilot import OpenAIPilot
from .research_eval import run_evaluation,VERSION
from ..market_data.providers.fx import YahooFxProvider


def main():
    if (os.environ.get('RUN_RESEARCH_EVAL') != 'enabled'
        or os.environ.get('GITHUB_REPOSITORY') != REPOSITORY
        or os.environ.get('GITHUB_REF') != 'refs/heads/phase-1/market-data-layer'
        or os.environ.get('GITHUB_EVENT_NAME') != 'push'):
        raise SystemExit('Research evaluation is disabled')
    path=Path('artifacts/research-eval/result.json')
    try:
        store=GitHubBudgetStore(os.environ.get('GH_BUDGET_TOKEN',''))
        state,_=store.load()
        prefix={key:value for key,value in state['entries'].items() if key.startswith(VERSION+':')}
        prior=None
        checkpoint=Path('docs/evaluations/research-eval-v1-checkpoint.json')
        if prefix:
            prior=json.loads(checkpoint.read_text())
            saved={c['request_id']:c for c in prior['calls']}
            if set(prefix)!=set(saved):
                raise RuntimeError('Unreconciled evaluation attempts; do not repeat paid calls')
            for key,row in prefix.items():
                record=saved[key]
                if (row['actual'] is None or row['actual']!=record['estimated_cost_microeur']
                    or row['usage'] is None or row['usage']['response_id']!=record['response_id']
                    or row['usage']['model']!=prior['model']
                    or row['usage']['cost_usd']!=record['cost_usd']):
                    raise RuntimeError('Unreconciled evaluation cost; no retry')
        key=os.environ.get('OPENAI_API_KEY','')
        if not key: raise ValueError('API key missing')
        now=datetime.now(timezone.utc)
        fx=YahooFxProvider().fetch('USD',now=now)
        client=OpenAIPilot(api_key=key,ledger=GitHubSpendingLedger(store),eur_per_usd=fx.eur_per_unit,enabled=True)
        report=run_evaluation(client,now=now,path=path,prior_report=prior)
        report['budget']=client.ledger.summary()
        report['fx']={'eur_per_usd':str(fx.eur_per_unit),'observed_at':fx.observed_at.isoformat(),'source':fx.source}
        path.write_text(json.dumps(report,indent=2)+'\n')
        print('EVALUATION_RESULT='+json.dumps(report))
        if not all(report['checks'].values()):
            raise RuntimeError('Evaluation quality checks failed')
    except Exception:
        if path.exists(): print('EVALUATION_PARTIAL='+path.read_text().replace('\n',''))
        raise SystemExit('Evaluation stopped; inspect report and persistent reservations before retrying.') from None


if __name__=='__main__': main()
