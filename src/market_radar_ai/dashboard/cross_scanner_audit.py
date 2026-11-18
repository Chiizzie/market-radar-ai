"""Read-only comparison of original published signals with contemporaneous AI traces.

No alert forwarding, candidate injection, provider orders or paid model access.
"""
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import requests

from ..agents.candidate_packages import digest
from ..agents.comparison_live import EventClient, envelope
from ..agents.paper_comparison import aware

SOURCE = 'https://raw.githubusercontent.com/Chiizzie/market-radar/radar-alert-live/radar_alert.json'
EXPERIMENT = digest({'version': 'cross-scanner-audit-v1', 'maximum_pair_gap_seconds': 600})
SIGNALS = {'ACTIONABLE NOW', 'WATCH FOR ENTRY', 'CHECK NOW'}


def fetch_original(session=None):
    session = session or requests.Session()
    response = session.get(SOURCE, timeout=(5, 12), stream=True, allow_redirects=False)
    try:
        if response.status_code != 200: raise ValueError('original_feed_unavailable')
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 12_000_000: raise ValueError('original_feed_capacity')
            chunks.append(chunk)
        raw = b''.join(chunks).decode('utf-8')
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get('schema_version') != 2:
            raise ValueError('original_feed_schema')
        return result
    finally:
        response.close()


def build(original, trace, qualification, *, now, decision=None):
    original_at = aware(original['generated_at'])
    ai_at = aware(qualification['evaluated_at'])
    gap = (ai_at-original_at).total_seconds()
    original_age = (aware(now)-original_at).total_seconds()
    ai_age = (aware(now)-ai_at).total_seconds()
    matched = abs(gap) <= 600 and 0 <= original_age <= 1800 and 0 <= ai_age <= 1800
    manifest = {r['symbol']: r for r in (trace or {}).get('symbols', [])}
    qualified = {r['candidate_id']: r for r in qualification.get('candidates', [])}
    rejected = {}
    for market, info in qualification.get('selection', {}).get('markets', {}).items():
        for r in info.get('rejected', []):
            rejected[market + ':' + r['symbol']] = r['reason']
    rows, seen = [], set()
    for row in original.get('potential_signals', []):
        q = row.get('qualification', {})
        if q.get('status') not in SIGNALS or not q.get('plan'): continue
        symbol = row.get('ticker') or row.get('symbol')
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9.-]{1,30}', symbol): continue
        market = 'stocks' if row.get('asset_type') == 'stock' else 'crypto'
        unmapped = False
        if market == 'crypto':
            from ..market_data.crypto_identities import IDENTITIES
            matches = [pair for pair, identity in IDENTITIES.items()
                       if identity[0] == symbol and identity[1].casefold() == str(row.get('name', '')).casefold()]
            if len(matches) == 1: symbol = matches[0]
            else: unmapped = True
        candidate = market + ':' + symbol
        if candidate in seen: continue
        seen.add(candidate)
        current, selection = qualified.get(candidate), manifest.get(symbol) if market == 'stocks' else None
        blocks = []
        if not matched: stage = 'no_contemporaneous_ai_capture'
        elif q.get('direction') == 'SHORT': stage = 'original_short_outside_ai_invest_scope'
        elif unmapped: stage = 'crypto_identity_not_mapped'
        elif decision and decision.get('candidate_id') == candidate and decision.get('schema_version') == 'paper-final-decision-v1':
            stage = 'ai_approved_watch' if decision.get('verdict') == 'PAPER_WATCH_FOR_ENTRY' else 'ai_review_no_action'
            blocks = decision.get('blockers', [])
        elif current:
            blocks = current.get('paper_blockers', [])
            stage = 'code_qualified_review_not_confirmed' if current.get('eligible_for_paper_review') else 'code_evidence_or_risk_blocked'
        elif candidate in rejected:
            stage, blocks = 'capture_rejected', [rejected[candidate]]
        elif selection:
            stage = selection['selection_reason']
        else: stage = 'no_symbol_trace'
        rows.append({'candidate_id': candidate, 'original_status': q['status'],
                     'original_pattern': q.get('pattern'), 'ai_stage': stage,
                     'blockers': blocks, 'selection_reason': selection.get('selection_reason') if selection else None,
                     'original_signal_id': digest({'at': original['generated_at'], 'symbol': symbol, 'qualification': q}),
                     'profit_or_loss_inferred': False})
    return {'schema_version': 'cross-scanner-audit-v1', 'as_of': aware(now).isoformat(),
            'dataset_kind': 'forward', 'trade_authorized': False, 'source': SOURCE,
            'source_sha256': digest(original), 'original_generated_at': original_at.isoformat(),
            'ai_evaluated_at': ai_at.isoformat(), 'capture_gap_seconds': gap,
            'timing_status': 'within_ten_minutes_not_identical_quotes' if matched else 'not_comparable',
            'original_signals': len(rows), 'stage_counts': dict(Counter(r['ai_stage'] for r in rows)),
            'rows': rows, 'model_calls': 0,
            'note': 'Published-feed comparison only; short-lived or overwritten alerts may be missed. '
                    'Different capture times and venues are retained. Missing traces are not AI rejections. '
                    'Original signals are neither proof of profit nor instructions for the AI scanner.'}


def main():
    import argparse, os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', type=Path, required=True)
    parser.add_argument('--review', type=Path)
    args = parser.parse_args()
    root = args.review or args.collection
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    try:
        original = fetch_original()
        trace_path = args.collection/'discovery-selection.json'
        trace = json.loads(trace_path.read_text()) if trace_path.exists() else None
        qpath = root/'qualification.json'
        if not qpath.exists(): qpath = args.collection/'qualification.json'
        decision_path = root/'decision.json'
        decision = json.loads(decision_path.read_text()) if decision_path.exists() else None
        report = build(original, trace, json.loads(qpath.read_text()), now=now, decision=decision)
        (root/'cross-scanner-audit.json').write_text(json.dumps(report, indent=2)+'\n')
        EventClient(os.environ.get('REVIEW_INGEST_SECRET')).append(EXPERIMENT, [envelope('audit', report, now)])
        status = {'state': 'audit_recorded', 'original_signals': report['original_signals'],
                  'timing_status': report['timing_status']}
    except (requests.RequestException, OSError, RuntimeError, ValueError, KeyError, TypeError):
        status = {'state': 'audit_unavailable', 'original_signals': None}
    status.update(model_calls=0, original_scanner_modified=False, trade_authorized=False)
    (root/'cross-scanner-status.json').write_text(json.dumps(status)+'\n')
    print(json.dumps(status))
    return int(status['state'] != 'audit_recorded')


if __name__ == '__main__': raise SystemExit(main())
