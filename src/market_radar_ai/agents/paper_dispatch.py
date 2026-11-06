"""Scheduled paper pipeline adapters; activation remains separately paused."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import json,os,subprocess,sys
from .paper_verdict import build_packets,run_pipeline
from .github_budget import GitHubBudgetStore,GitHubSpendingLedger
from .openai_pilot import OpenAIPilot
from ..market_data.providers.fx import YahooFxProvider


def execute(document,feed,root,*,env,clock=lambda:datetime.now(timezone.utc)):
    from .scheduled_review import permitted
    if not permitted(env,clock()) or env.get('PAPER_FINAL_VERDICTS')!='true':
        raise ValueError('paper_dispatch_disabled')
    root=Path(root)
    if root.exists():raise ValueError('preserve_existing_paper_attempt')
    # Qualification chooses the appropriate per-market strategy. Crypto is not
    # held behind a US-stock timer; stock opening bars are independently checked.
    batch=build_packets(document,feed,now=clock())
    if env.get('PAPER_WATCHER_ENABLED')=='false':
        root.mkdir(parents=True)
        status={'state':'paper_watcher_disabled_zero_cost','model_calls':0,'trade_authorized':False}
        (root/'status.json').write_text(json.dumps(status)+'\n')
        return status
    if not batch['packets']:
        root.mkdir(parents=True)
        status={'state':'no_qualified_candidate_zero_cost','model_calls':0,'trade_authorized':False}
        (root/'status.json').write_text(json.dumps(status)+'\n')
        (root/'qualification.json').write_text(json.dumps(batch['qualification'],indent=2)+'\n')
        from .paper_comparison import cohort_snapshot
        (root/'comparison-cohort.json').write_text(json.dumps(cohort_snapshot([],now=clock()),indent=2)+'\n')
        return status
    fx=YahooFxProvider().fetch('USD',now=clock())
    client=OpenAIPilot(api_key=env.get('OPENAI_API_KEY'),ledger=GitHubSpendingLedger(GitHubBudgetStore(env.get('GH_BUDGET_TOKEN'))),
                      eur_per_usd=fx.eur_per_unit,enabled=True,count_input_tokens=True)
    def refresh(symbol):
        from ..dashboard.scheduled_collection import run_cycle
        clean={**env,'SCANNER_COLLECTION_MODE':'scheduled','ENABLE_STOCK_DISCOVERY':'true',
               'SCREEN_DISCOVERY_DATA':'true','ENABLE_STOCK_CHECKS':'true'}
        for k in ('OPENAI_API_KEY','OPEN_API_KEY','GH_BUDGET_TOKEN','GH_PAPER_TOKEN'):clean.pop(k,None)
        process_env={**os.environ,**clean}
        for k in ('OPENAI_API_KEY','OPEN_API_KEY','GH_BUDGET_TOKEN','GH_PAPER_TOKEN'):process_env.pop(k,None)
        def stage(module,args):
            return subprocess.run([sys.executable,'-m','market_radar_ai.'+module,*map(str,args)],
                                  env=process_env,timeout=240,check=False).returncode
        output=root/'fresh-collector'
        run_cycle(env=clean,output=output,cache_path=root/'fresh-cache.json',clock=clock,run=stage,
                  delivery=lambda *a,**k:{'state':'internal_paper_revalidation_only'},stock_symbols=('MU',) if symbol in ('XBTEUR','ETHEUR','SOLEUR','XRPEUR') else (symbol,))
        return json.loads((output/'enriched-capture.json').read_text()),json.loads((output/'news.json').read_text())
    def delivery(archive):
        from ..dashboard.paper_final_delivery import deliver
        watch_env={**env,'SCANNER_COLLECTION_MODE':'scheduled'}
        for k in ('OPENAI_API_KEY','OPEN_API_KEY','GH_BUDGET_TOKEN'):watch_env.pop(k,None)
        if archive['decision']['verdict'] == 'PAPER_WATCH_FOR_ENTRY':
            from .github_paper_tracking import update
            update(env.get('GH_PAPER_TOKEN'),now=clock(),decision=archive['decision'])
            from .paper_watcher import poll_once
            from .paper_observer import ReferenceObserver
            observer=ReferenceObserver(watch_env,clock=clock)
            # Start observing before dashboard/Telegram delivery can consume the
            # short entry window. Notification follows the original watch alert.
            armed=poll_once(env=watch_env,observer=observer,clock=clock,notifications=False)
            (root/'paper-tracking.json').write_text(json.dumps(armed['report'],indent=2)+'\n')
        try:
            return deliver(archive,env=env,clock=clock)
        finally:
            if archive['decision']['verdict'] == 'PAPER_WATCH_FOR_ENTRY':
                from .paper_watcher import run
                # Bridge the entire entry window even if the next runner is late.
                # The independent overlapping watcher continues open positions.
                run(env=watch_env,output=root/'entry-watcher',duration=65,
                    clock=clock,observer=observer)
    return run_pipeline(document,feed,client=client,root=root,refresh=refresh,deliver=delivery,clock=clock,enabled=True)
