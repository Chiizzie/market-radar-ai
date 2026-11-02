"""Manual stock or crypto research runner. Dry-run by default; no orders or plan approval."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from .github_budget import GitHubBudgetStore, GitHubSpendingLedger, REPOSITORY
from .openai_pilot import OpenAIPilot
from .combined_input import build_combined_input
from .crypto_input import build_crypto_input, PAIRS
from .crypto_news_input import build_crypto_news_input, PROVIDER_SYMBOLS
from ..evidence.news import NewsProvider
from ..market_data.providers.kraken import KrakenProvider
from .live_research import preflight, run_research
from ..market_data.capture import capture_markets
from ..market_data.providers.yahoo import YahooFinanceProvider
from ..market_data.providers.fx import YahooFxProvider
from ..evidence.public_feed import fetch_feed


def execute(directory, *, env, clock=lambda:datetime.now(timezone.utc)):
    if (env.get('GITHUB_REPOSITORY')!=REPOSITORY
            or env.get('GITHUB_REF')!='refs/heads/phase-1/market-data-layer'
            or env.get('GITHUB_EVENT_NAME')!='workflow_dispatch'):
        raise ValueError('Manual development-branch execution required')
    mode=env.get('LIVE_RESEARCH_MODE','dry_run')
    if mode not in ('dry_run','paid'):
        raise ValueError('Invalid mode')
    if mode=='paid' and (env.get('ENABLE_LIVE_RESEARCH')!='enabled'
            or env.get('GITHUB_RUN_ATTEMPT')!='1'):
        raise ValueError('Paid activation absent or workflow rerun blocked')
    target=env.get('RESEARCH_TARGET','NVDA')
    if target not in ('NVDA',*PAIRS):
        raise ValueError('Unsupported research target')
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    if (root/'status.json').exists() or (root/'analysis.json').exists():
        raise ValueError('Existing run artifacts must be preserved')
    status={'state':'preparing','mode':mode,'target':target,'trade_authorized':False}
    def save(name,value):
        (root/name).write_text(json.dumps(value,indent=2)+'\n')
    save('status.json',status)
    try:
        if target=='NVDA':
            capture=capture_markets(['NVDA'],[],stock_fetch=lambda symbol:
                YahooFinanceProvider().fetch_history(symbol,period='1d',interval='5m'),crypto_fetch=None)
            save('capture.json',capture)
            news=fetch_feed(source='nvidia');save('news.json',news)
            packet=build_combined_input(capture,news,symbol=target,now=clock())
        else:
            capture=capture_markets([],[target],stock_fetch=None,
                crypto_fetch=lambda pair:KrakenProvider().fetch_ohlc(pair,interval_minutes=5))
            save('capture.json',capture)
            packet=build_crypto_input(capture,symbol=target,now=clock())
            news_key=env.get('ALPHA_VANTAGE_API_KEY','').strip()
            news=({'status':'not_connected','items':[], 'scope':'CRYPTO_NEWS_NOT_CONFIGURED'}
                  if not news_key else NewsProvider(api_key=news_key).fetch(symbol=PROVIDER_SYMBOLS[target]))
            save('news.json',news)
            status['news_evidence']='unavailable'
            if news_key:
                try:
                    packet=build_crypto_news_input(capture,news,symbol=target,now=clock())
                    status['news_evidence']='partial'
                except (ValueError,TypeError,KeyError,AttributeError):
                    status['news_evidence']='unusable'
                    # Keep valid candles and the explicit missing-news gap.
                    # The source artifact records failure; no title is fabricated.
            save('status.json',status)
        preflight(packet,now=clock())
        save('input.json',{'snapshot_id':packet.digest(),'input':packet.model_dump(mode='json'),
                           'trade_authorized':False})
        if mode=='dry_run':
            status.update(state='ready_dry_run',model_calls=0)
        else:
            key=env.get('OPENAI_API_KEY','')
            token=env.get('GH_BUDGET_TOKEN','')
            if not key or not token:raise ValueError('Missing runner credentials')
            fx=YahooFxProvider().fetch('USD',now=clock())
            preflight(packet,now=clock())
            store=GitHubBudgetStore(token)
            ledger=GitHubSpendingLedger(store)
            before=ledger.summary()
            save('budget-before.json',before)
            save('cost-fx.json',{'eur_per_usd':str(fx.eur_per_unit),
                'observed_at':fx.observed_at.isoformat(),'source':fx.source,
                'purpose':'AI cost accounting only; market candles remain native currency'})
            client=OpenAIPilot(api_key=key,ledger=ledger,eur_per_usd=fx.eur_per_unit,enabled=True)
            result=run_research(client,packet,path=root/'analysis.json',clock=clock,enabled=True)
            save('budget-after.json',ledger.summary())
            status.update(state=result['state'],model_calls=len(result['calls']))
    except Exception:
        # The analysis/ledger retain attempts and known usage. Do not imply a
        # failed run cost zero, and never expose provider exceptions or secrets.
        status.update(state='blocked_or_failed',reason='Inspect evidence and analysis artifacts; do not retry automatically')
        save('status.json',status)
        raise RuntimeError('Research runner stopped; inspect saved artifacts and shared ledger') from None
    save('status.json',status)
    return status


def main():
    try:
        result=execute('artifacts/live-research',env=os.environ)
        print(json.dumps(result))
    except Exception:
        raise SystemExit('Research stopped or disabled; inspect artifacts. No automatic retry.') from None


if __name__=='__main__':main()
