"""Create an allowlisted dashboard snapshot from a version-2 market capture."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..market_data.models import ProviderResult
from ..market_data.quality import validate_candles


def build_snapshot(document, *, now):
    if now.tzinfo is None or document.get('format_version') != 2:
        raise ValueError('Aware clock and capture format version 2 required')
    markets = {'stocks': [], 'crypto': []}
    for capture in document['captures']:
        p = capture['payload']
        canonical = json.dumps(p, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        if hashlib.sha256(canonical.encode()).hexdigest() != capture['payload_sha256']:
            raise ValueError('Capture checksum mismatch')
        result = ProviderResult(provider=p['provider'], retrieved_at=p['retrieved_at'],
            status=p['provider_status'], candles=p['candles'])
        rows = result.candles
        latest = max((c.timestamp for c in rows), default=None)
        issues = validate_candles(rows, now=now, max_age_seconds=900, expected_interval_seconds=300)
        valid_identity = all(c.symbol.upper() == capture['requested_symbol'].upper()
            and c.source == result.provider and c.interval == '5m' for c in rows)
        current = (result.status == 'ok' and p['quality_passed_at_capture']
            and not p['quality_issues'] and not issues and valid_identity and bool(rows)
            and all((now-c.timestamp).total_seconds() >= 300 for c in rows)
            and 0 <= (now-result.retrieved_at).total_seconds() <= 900)
        # Deliberately do not pass through arbitrary text, credentials, or raw provider errors.
        markets[capture['market']].append({
            'symbol': capture['requested_symbol'], 'provider': result.provider,
            'status': 'CURRENT_RESEARCH_DATA' if current else 'UNUSABLE_OR_STALE',
            'retrieved_at': result.retrieved_at.isoformat(),
            'latest_candle_at': latest.isoformat() if latest else None,
            'latest_candle_age_seconds': (now-latest).total_seconds() if latest else None,
            'candles_saved': len(rows),
            'quote_currencies': sorted(set(c.quote_currency for c in rows)),
            'broker_eligibility': 'UNKNOWN', 'decision': 'NO_ACTION'})
    return {'schema_version': '1.0', 'mode': 'RESEARCH_ONLY',
        'generated_at_dublin': now.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
        'expires_at_epoch': int(now.timestamp()) + 60,
        'display_currency': 'EUR', 'coverage_scope': 'REQUESTED_SYMBOLS_ONLY',
        'markets': markets, 'agents': {'status': 'NOT_RUN_ON_THIS_CAPTURE', 'reports': []},
        'paper_outcomes': None, 'api_budget': None, 'live_orders_enabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    snapshot = build_snapshot(json.loads(args.capture.read_text()), now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2)+'\n')


if __name__ == '__main__':
    main()
