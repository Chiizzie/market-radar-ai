"""Create an allowlisted dashboard snapshot from a version-2 market capture."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..market_data.models import ProviderResult
from ..market_data.quality import validate_candles


def build_snapshot(document, *, now, evidence=None):
    from .evidence import export_evidence
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
    coverage = {}
    for market, rows in markets.items():
        source = document['coverage'][market]
        requested, attempted = source['requested'], source['attempted']
        deferred = source['deferred']
        if (type(requested) is not int or type(attempted) is not int
                or not isinstance(deferred, list) or any(not isinstance(s, str) for s in deferred)
                or attempted != len(rows) or requested != attempted + len(deferred)
                or len({r['symbol'] for r in rows}) != len(rows)):
            raise ValueError('Inconsistent capture coverage')
        queue = document.get('queue_selection', {}).get(market)
        universe_count = requested
        if queue is not None:
            universe_count = queue['universe_count']
            if (type(universe_count) is not int or universe_count < requested
                    or set(queue['selected']) != {r['symbol'] for r in rows} | set(deferred)
                    or queue['deferred_count'] != universe_count-requested):
                raise ValueError('Inconsistent queue coverage')
        coverage[market] = {'universe_count': universe_count,
            'attempted': attempted, 'deferred': universe_count-attempted,
            'current': sum(r['status']=='CURRENT_RESEARCH_DATA' for r in rows),
            'unusable_or_stale': sum(r['status']!='CURRENT_RESEARCH_DATA' for r in rows),
            'agent_reviewed': 0}
    snapshot = {'schema_version': '1.0', 'mode': 'RESEARCH_ONLY',
        'generated_at_dublin': now.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
        'expires_at_epoch': int(now.timestamp()) + 60,
        'display_currency': 'EUR', 'coverage_scope': 'REQUESTED_SYMBOLS_ONLY',
        'coverage': coverage, 'markets': markets, 'agents': {'status': 'NOT_RUN_ON_THIS_CAPTURE', 'reports': []},
        'evidence': export_evidence(evidence, now=now),
        'paper_outcomes': None, 'api_budget': None, 'live_orders_enabled': False}
    if 'stock_context' in document:
        from .briefing import build_briefing
        snapshot['research_briefing']=build_briefing(document,evidence,now=now)
    if document.get("stock_context") or "paper_tracking_report" in document:
        from .diagnostics import build_diagnostics
        snapshot["research_diagnostics"] = build_diagnostics(document, now=now)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    snapshot = build_snapshot(json.loads(args.capture.read_text()), now=datetime.now(timezone.utc),
        evidence=json.loads(args.evidence.read_text()) if args.evidence else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2)+'\n')


if __name__ == '__main__':
    main()
