"""Prepare future paired inputs using Python only; no model, provider or alert clients."""
import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path

from .candidate_packages import canonical
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--news', type=Path, required=True)
    parser.add_argument('--library', type=Path, default=Path('knowledge/library-20261113.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(UTC)
    args.output.mkdir(parents=True, exist_ok=True)
    if now < aware(VALIDATION_START):
        result = prepare({}, {}, {}, now=now)
    else:
        result = prepare(bounded_json(args.capture,4_000_000), bounded_json(args.news,2_000_000),
                         bounded_json(args.library,8_000_000), now=now)
    pairs = result.pop('pairs')
    (args.output/'paired-inputs.json').write_text(canonical(pairs)+'\n')
    (args.output/'summary.json').write_text(canonical(result)+'\n')
    print(canonical(result))


if __name__ == '__main__':
    main()
