"""Fresh public candles/FX plus authenticated catalogue; zero paid AI calls."""
from datetime import datetime,timezone
from pathlib import Path
import json
from .paper_planner import draft_nvda
from ..market_data.providers.yahoo import YahooFinanceProvider
from ..market_data.providers.fx import YahooFxProvider


def main():
    output=Path('artifacts/paper-rehearsal/result.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        catalogue=json.loads(Path('artifacts/broker-check/result.json').read_text())
        market=YahooFinanceProvider().fetch_history('NVDA',period='1d',interval='5m')
        if market.status!='ok' or market.issues: raise ValueError()
        fx=YahooFxProvider().fetch('USD')
        result=draft_nvda(market.candles,catalogue,fx,now=datetime.now(timezone.utc),
                         paper_capital_eur=500,round_trip_cost_bps=40)
        result['assumptions_note']='EUR 500 fictional paper allocation and 40 bps round-trip cost allowance; neither is a verified account balance or broker fee quote.'
    except Exception:
        result=dict(state='blocked',trade_authorized=False,paper_only=True,model_calls=0,
                    failures=['fresh_evidence_unavailable'],plan=None)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'state':result['state'],'failures':result.get('failures',[]),'trade_authorized':False}))
    return 0  # A recorded no-plan decision is valid; inspect result state, not exit code.

if __name__=='__main__':raise SystemExit(main())
