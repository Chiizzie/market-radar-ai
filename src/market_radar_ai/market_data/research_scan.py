"""Run a bounded public-data research scan. Unverified broker assets are rejected."""
import argparse
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .providers.catalogues import KrakenCatalogue
from .providers.kraken import KrakenProvider
from .batch import fetch_batch
from .screening import ScreeningInput, screen_batch


def run_scan(limit=5):
    if not 1 <= limit <= 20:
        raise ValueError('Public smoke scan limit must be 1..20')
    catalogue = KrakenCatalogue().discover_eur()
    if catalogue.status != 'ok':
        return {'status': 'error', 'issues': [i.model_dump(mode='json') for i in catalogue.issues]}
    provider = KrakenProvider()
    symbols = sorted(i.symbol for i in catalogue.instruments)
    batch = fetch_batch(symbols, provider.fetch_ohlc, max_symbols=limit, max_seconds=120)
    by_symbol = {i.symbol: i for i in catalogue.instruments}
    now = datetime.now(timezone.utc)
    screened = screen_batch([ScreeningInput(by_symbol[s], data) for s, data in batch.results.items()], now=now)
    return {
        'status': 'research_only', 'as_of': now.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
        'catalogue_count': len(symbols), 'attempted': len(batch.results),
        'deferred_count': len(batch.deferred), 'duplicate_count': batch.duplicate_count,
        'provider_metrics': provider.client.metrics(), 'screening': screened.report.as_dict(),
        'results': {s: {'status': r.status, 'candle_count': len(r.candles),
                         'latest': max((c.timestamp for c in r.candles), default=None).isoformat() if r.candles else None,
                         'admission_failures': screened.admissions[s].failures}
                    for s, r in batch.results.items()},
        'note': 'No broker evidence supplied. No trade recommendations or AI calls.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    result = run_scan(args.limit)
    print(json.dumps(result, indent=2))
    return int(result['status'] == 'error' or any(r['status'] != 'ok' for r in result.get('results', {}).values()))


if __name__ == '__main__':
    raise SystemExit(main())
