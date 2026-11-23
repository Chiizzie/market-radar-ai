"""Prepare future paired inputs using Python only; no model, provider or alert clients."""
import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path

from .candidate_packages import canonical, digest
from .knowledge_cases import library_summary, validate_library
from .knowledge_pair import PROTOCOL_ID, VALIDATION_START, prepare_pair
from .knowledge_playbooks import RULES
from .paper_comparison import aware
from .paper_verdict import build_packets


def prepare(document, feed, library, *, now):
    now = aware(now)
    summary = {'protocol_id':PROTOCOL_ID, 'as_of':now.isoformat(), 'model_calls':0,
               'trade_authorized':False, 'pairs':[], 'state':'outside_validation_period'}
    if now < aware(VALIDATION_START):
        return summary
    validate_library(library)
    summary['library'] = library_summary(library)
    qualified = build_packets(document, feed, now=now)
    packets = qualified['packets']
    summary.update(state='prepared', code_qualified=len(packets), unsupported_strategy=0,
                   paper_blockers=dict(Counter(b for r in qualified['qualification']['candidates']
                                              for b in r.get('paper_blockers',[]))))
    for packet in packets:
        if (not packet['packet']['candidate_id'].startswith('stocks:')
                or packet['packet']['technical_checks'].get('strategy_id') not in RULES):
            summary['unsupported_strategy'] += 1
            continue
        summary['pairs'].append(prepare_pair(packet, library, now=now))
    summary['paired_inputs'] = len(summary['pairs'])
    return summary


def bounded_json(path, maximum):
    if path.stat().st_size > maximum:
        raise ValueError('knowledge_input_capacity')
    return json.loads(path.read_text())


def prepare_captured(document, feed, library, captured, *, now):
    """Keep original research inputs without turning old quotes into live evidence.

    Reproduce the collector's complete packet set at its recorded qualification
    clock. Processing time is recorded separately. These saved inputs are never
    accepted by the paid/live pair adapter, even if their old expiry is in range.
    """
    now = aware(now)
    if (captured.get('trade_authorized') is not False or captured.get('model_calls') != 0
            or not isinstance(captured.get('packets'), list)):
        raise ValueError('captured_knowledge_scope')
    qualification = captured['qualification']
    if (qualification.get('schema_version') != 'free-qualification-v1'
            or qualification.get('trade_authorized') is not False):
        raise ValueError('captured_knowledge_qualification')
    original = aware(qualification['evaluated_at'])
    if original > now:
        raise ValueError('captured_knowledge_from_future')
    rebuilt = build_packets(document, feed, now=original)
    if canonical(rebuilt['packets']) != canonical(captured['packets']):
        raise ValueError('captured_knowledge_packets_do_not_reproduce')
    result = prepare(document, feed, library, now=original)
    for pair in result['pairs']:
        pair.update(prepared_at=now.isoformat(), source_qualified_at=original.isoformat(),
                    input_use='offline_captured_preparation_only')
    result.update(state='captured_inputs_prepared', as_of=now.isoformat(), source_qualified_at=original.isoformat(),
                  source_age_seconds=(now-original).total_seconds(),
                  input_use='offline_captured_preparation_only', live_review_ready=False,
                  original_packet_count=len(captured['packets']),
                  source_sha256={'capture':digest(document), 'news':digest(feed),
                                 'packets':digest(captured)},
                  note='Original collector inputs reproduced; processing is later. '
                       'No model decision or live freshness is backdated. Paid review requires fresh preparation.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--news', type=Path, required=True)
    parser.add_argument('--packets', type=Path, help='Original collector packets; offline preparation only.')
    parser.add_argument('--library', type=Path, default=Path('knowledge/library-20261113.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(UTC)
    args.output.mkdir(parents=True, exist_ok=True)
    if now < aware(VALIDATION_START):
        result = prepare({}, {}, {}, now=now)
    else:
        document = bounded_json(args.capture,4_000_000)
        feed = bounded_json(args.news,2_000_000)
        library = bounded_json(args.library,8_000_000)
        if args.packets:
            captured = bounded_json(args.packets,20_000_000)
            result = prepare_captured(document, feed, library, captured, now=now)
            from .manual_plan_preflight import assess_packets
            feasibility = assess_packets(captured['packets'],
                source_at=aware(captured['qualification']['evaluated_at']), processed_at=now)
            (args.output/'manual-feasibility.json').write_text(canonical(feasibility)+'\n')
        else:
            result = prepare(document, feed, library, now=now)
    pairs = result.pop('pairs')
    (args.output/'paired-inputs.json').write_text(canonical(pairs)+'\n')
    (args.output/'summary.json').write_text(canonical(result)+'\n')
    print(canonical(result))


if __name__ == '__main__':
    main()
