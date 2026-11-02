"""Explicit, read-only provider smoke checks. Never submits orders or calls AI."""
import argparse
import json
from zoneinfo import ZoneInfo
from .providers import CoinGeckoProvider, KrakenProvider, YahooFinanceProvider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['coingecko', 'kraken', 'yahoo', 'all'], default='coingecko')
    parser.add_argument('--crypto-limit', type=int, default=20)
    args = parser.parse_args()
    checks = {
        'coingecko': lambda: CoinGeckoProvider().discover_eur_markets(limit=args.crypto_limit),
        'kraken': lambda: KrakenProvider().fetch_ohlc('XBTEUR'),
        'yahoo': lambda: YahooFinanceProvider().fetch_history('MSFT'),
    }
    results = []
    for name, check in checks.items():
        if args.provider not in (name, 'all'):
            continue
        result = check()
        results.append({
            'provider': result.provider, 'status': result.status,
            'retrieved_at': result.retrieved_at.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
            'instrument_count': len(result.instruments), 'candle_count': len(result.candles),
            'latest_candle': result.candles[-1].timestamp.isoformat() if result.candles else None,
            'issues': [issue.model_dump(mode='json') for issue in result.issues],
        })
    print(json.dumps(results, indent=2))
    return int(any(r['status'] != 'ok' or not (r['instrument_count'] or r['candle_count']) for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
