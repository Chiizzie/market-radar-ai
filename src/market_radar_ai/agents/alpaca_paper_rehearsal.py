"""Join fresh read-only captures into an unapproved EUR paper draft."""
from datetime import datetime, timezone
import json
from pathlib import Path

from .paper_planner import draft_nvda
from ..market_data.providers.fx import YahooFxProvider


def build(capture, catalogue, fx, *, now):
    result = dict(version='alpaca-paper-rehearsal-v1', state='blocked',
                  trade_authorized=False, paper_only=True, model_calls=0,
                  evaluated_at=now.isoformat(), failures=[], plan=None)
    try:
        observed=datetime.fromisoformat(capture['observed_at'])
        if not 0 <= (now-observed).total_seconds() <= 300:
            raise ValueError()
        if (capture['version']!='alpaca-data-check-v1' or capture['symbol']!='NVDA'
                or capture['feed']!='iex' or capture['currency']!='USD'
                or capture['trade_authorized'] is not False):
            raise ValueError()
        if capture['bars']['status']!='fresh':
            raise ValueError()
        candles=capture['bars']['candles']
        if any(c['source']!='alpaca_iex' for c in candles):
            raise ValueError()
    except (KeyError,TypeError,ValueError):
        result['failures']=['alpaca_capture_invalid_or_stale']
        return result
    result=draft_nvda(candles,catalogue,fx,now=now,paper_capital_eur=500,round_trip_cost_bps=40,calendar=capture.get('calendar'))
    result['assumptions_note']='EUR 500 fictional paper allocation; 40 bps assumed round-trip costs. Neither is an account balance or verified broker fee.'
    result['capture_observed_at']=capture['observed_at']
    result['quote_context']=capture.get('quote',{})
    result['news_context']={k:capture.get('news',{}).get(k) for k in ('status','count','more_available','catalysts_verified')}
    # Quote/news are context only: neither clears execution, cost or catalyst gates.
    return result


def main():
    stage='capture_load'
    try:
        capture=json.loads(Path('artifacts/alpaca-check/result.json').read_text())
        catalogue=json.loads(Path('artifacts/broker-check/result.json').read_text())
        stage='fx_fetch'
        fx=YahooFxProvider().fetch('USD')
        stage='paper_draft'
        result=build(capture,catalogue,fx,now=datetime.now(timezone.utc))
        result['fx_evidence']=fx.model_dump(mode='json')
    except Exception:
        result=dict(state='blocked',trade_authorized=False,paper_only=True,model_calls=0,
                    failures=[stage+'_failed'],plan=None)
    target=Path('artifacts/alpaca-paper/result.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__': main()
