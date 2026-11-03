"""Explain live research readiness and rehearse expiry without orders or AI."""
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from ..agents.candidate_packages import build_packages, verify_package
from ..dashboard.export import build_snapshot
from .reference_quotes import validate_capture


def readiness(document, feed, *, now):
    snapshot = build_snapshot(document, now=now, evidence=feed)
    batch = build_packages(document, feed, now=now)
    local = now.astimezone(ZoneInfo('Europe/Dublin'))
    cutoff = local.replace(hour=22, minute=0, second=0, microsecond=0)
    reference = {'status': 'not_supplied', 'pairs': []}
    raw = document.get('reference_quote_capture')
    if raw is not None:
        try:
            quotes = validate_capture(raw, now=now)
            reference = {'status': 'current_reference_only', 'pairs': list(quotes),
                         'broker_executable': False}
        except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
            reference = {'status': 'unavailable_invalid_or_stale', 'pairs': []}
    candidates = []
    for record in batch['packages']:
        body = verify_package(record, now=now)
        expiry = datetime.fromisoformat(body['expires_at'])
        try:
            verify_package(record, now=expiry)
        except ValueError:
            expiry_rejected = True
        else:
            raise ValueError('package_expiry_guard_failed')
        candidates.append({'candidate_id': body['candidate_id'], 'package_id': record['package_id'],
            'research_ready_at_check': True, 'trade_ready': False,
            'expires_at': body['expires_at'], 'news_sources': len(body['news_source_ids']),
            'context_only_news': len(body['context_only_news_ids']),
            'missing_evidence': body['missing_evidence'],
            'expiry_replay': {'tested_at': expiry.isoformat(), 'rejected': expiry_rejected,
                              'kind': 'DETERMINISTIC_GUARD_TEST_NOT_FUTURE_OBSERVATION'}})
    # Re-evaluate original captures, never extend timestamps to make data pass.
    later = build_snapshot(document, now=now+timedelta(minutes=16))
    stale_rejected = all(v['current'] == 0 for v in later['coverage'].values())
    if not stale_rejected:
        raise ValueError('capture_staleness_guard_failed')
    return {'schema_version': 'research-readiness-v1', 'evaluated_at_dublin': local.isoformat(),
        'mode': 'AFTER_CUTOFF_RESEARCH_ONLY' if local >= cutoff else 'RESEARCH_ONLY',
        'entry_window_open': local < cutoff,
        'entry_window_note': 'Time gate only; does not verify exchange session or admit a trade.',
        'coverage': snapshot['coverage'], 'selection': batch['selection']['markets'],
        'providers': sorted({c['payload']['provider'] for c in document['captures']}),
        'reference_quotes': reference, 'candidates': candidates,
        'news': {'status': snapshot['evidence']['status'],
                 'items': len(snapshot['evidence']['items']), 'coverage_complete': False},
        'capture_expiry_replay': {'tested_at': (now+timedelta(minutes=16)).isoformat(),
            'all_original_captures_rejected': stale_rejected,
            'kind': 'DETERMINISTIC_GUARD_TEST_NOT_FUTURE_OBSERVATION'},
        'model_calls': 0, 'trade_authorized': False, 'orders_submitted': 0,
        'stock_warmup': {'minimum_completed_5m_bars': 20,
            'current_session_minutes_required': 100,
            'note': 'For current-session Alpaca bars, 20 complete bars require at least 100 minutes after open; missing bars can delay readiness.'}}


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.capture.stat().st_size > 4_000_000 or args.evidence.stat().st_size > 2_000_000:
        raise ValueError('input_too_large')
    result = readiness(json.loads(args.capture.read_text()), json.loads(args.evidence.read_text()),
                       now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('mode', 'coverage', 'reference_quotes', 'model_calls', 'trade_authorized')}))


if __name__ == '__main__':
    main()
