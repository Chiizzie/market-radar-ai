"""Cheap capture discovery, deliberately separate from broker/trade admission."""
from .limits import STOCK_RESEARCH_LIMIT, CRYPTO_RESEARCH_LIMIT
from dataclasses import asdict
from .models import Candle, Instrument
from .screener import rank_candidates
from .strategy_window import profile
from ..dashboard.export import build_snapshot


def shortlist(document, *, now, stock_limit=3, crypto_limit=2):
    if any(type(n) is not int or not 1 <= n <= bound for n,bound in ((stock_limit,STOCK_RESEARCH_LIMIT),(crypto_limit,CRYPTO_RESEARCH_LIMIT))):
        raise ValueError('shortlist_limits_exceeded')
    snapshot = build_snapshot(document, now=now)  # verifies hashes and freshness
    output = {}
    for market, limit in (('stocks', stock_limit), ('crypto', crypto_limit)):
        status = {r['symbol']: r['status'] for r in snapshot['markets'][market]}
        instruments, series, rejected = [], {}, []
        for capture in document['captures']:
            if capture['market'] != market: continue
            symbol = capture['requested_symbol']
            rows = [Candle.model_validate(c) for c in capture['payload']['candles']]
            reason = ('unusable_or_stale' if status[symbol] != 'CURRENT_RESEARCH_DATA'
                else 'insufficient_history' if profile(rows, now=now) is None
                else 'mixed_quote_currency' if len({c.quote_currency for c in rows}) != 1
                else 'no_baseline_participation' if sum(c.volume for c in (rows[-20:-5] if len(rows)>=20 else rows[:-3])) <= 0
                else None)
            if reason:
                rejected.append({'symbol': symbol, 'reason': reason}); continue
            instruments.append(Instrument(symbol=symbol, asset_class='equity' if market=='stocks' else 'crypto',
                quote_currency=rows[0].quote_currency, venue=capture['payload']['provider']))
            series[symbol] = rows
        ranked = sorted([score for instrument in instruments for score in rank_candidates(
            [instrument], series, min_candles=20 if len(series[instrument.symbol])>=20 else len(series[instrument.symbol]))], key=lambda r:r.score, reverse=True)
        candidates = []
        for row in ranked[:limit]:
            candidates.append({**asdict(row), 'decision': 'RESEARCH_SHORTLIST_ONLY',
                'broker_eligibility': 'UNKNOWN', 'trade_authorized': False,
                'quote_currency': series[row.symbol][0].quote_currency,
                'latest_candle_at': series[row.symbol][-1].timestamp.isoformat(),
                'admission_required': ['account_specific_broker_eligibility',
                    'executable_prices_and_costs', 'eur_risk_plan', 'session_and_expiry',
                    'independent_catalyst_evidence', 'six_agent_review']})
        output[market] = {'attempted': len(status), 'rankable': len(ranked),
            'shortlisted': len(candidates), 'deferred_by_limit': len(ranked)-len(candidates),
            'rejected': rejected, 'candidates': candidates}
    return {'schema_version': 'capture-shortlist-v1', 'evaluated_at': now.isoformat(),
        'expires_at_epoch': snapshot['expires_at_epoch'], 'scope': 'REQUESTED_SYMBOLS_ONLY',
        'ranking_basis': '20-bar momentum or contiguous opening-session bars (minimum six): capped momentum plus capped relative volume; not win probability',
        'model_calls': 0, 'trade_authorized': False, 'markets': output}


def main():
    import argparse, json
    from datetime import datetime, timezone
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = shortlist(json.loads(args.capture.read_text()), now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:{f:v[f] for f in ('attempted','rankable','shortlisted','deferred_by_limit')}
                      for k,v in result['markets'].items()}))


if __name__ == '__main__': main()
