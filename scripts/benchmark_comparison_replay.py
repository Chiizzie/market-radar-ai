"""Replay a saved, authenticated event export without providers or model calls.

Run with PYTHONPATH=src. An optional pre-change paper_comparison.py provides an
equivalence/speed comparison; it must use the same protocol and decision rules.
The archive is only read, and disposable projections are removed after the run.
"""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from contextlib import contextmanager
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

from market_radar_ai.agents import comparison_live
from market_radar_ai.agents.candidate_packages import canonical
from market_radar_ai.agents.paper_comparison import aware


class ArchiveClient:
    def __init__(self, events, page_size):
        self.partitions = defaultdict(list)
        for event in events:
            self.partitions[(event['experiment_id'], event['day'])].append(event)
        self.sequences = {key: [event['seq'] for event in value]
                          for key, value in self.partitions.items()}
        # Do not silently sort or deduplicate evidence: the normal reader must
        # reject malformed ordering and hashes just as the live process does.
        for sequences in self.sequences.values():
            if any(type(seq) is not int for seq in sequences) or any(
                    left >= right for left, right in zip(sequences, sequences[1:])):
                raise ValueError('comparison_event_order')
        self.page_size = page_size

    def read(self, experiment, day, after):
        key = (experiment, day)
        index = bisect_right(self.sequences.get(key, []), after)
        events = self.partitions.get(key, [])[index:index + self.page_size]
        return {'events': events, 'next': events[-1]['seq'] if events else after}


@contextmanager
def projection_class(baseline_path):
    original = comparison_live.ComparisonStore
    if baseline_path is not None:
        spec = importlib.util.spec_from_file_location(
            'market_radar_ai.agents._benchmark_baseline', baseline_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        comparison_live.ComparisonStore = module.ComparisonStore
    try:
        yield
    finally:
        comparison_live.ComparisonStore = original


def measure(events, *, page_size, baseline_path=None):
    client = ArchiveClient(events, page_size)
    now = max(aware(event['occurred_at']) for event in events)
    reports, exports, health = {}, {}, {}
    seconds = 0.0
    with TemporaryDirectory(prefix='comparison-benchmark-') as root, projection_class(baseline_path):
        for day in sorted({event['day'] for event in events}):
            worker = comparison_live.LiveComparison(Path(root) / day, client=client,
                                                    day=day, clock=lambda: now)
            start = perf_counter()
            worker.sync()
            seconds += perf_counter() - start
            reports[day] = worker.store.report(now=now)
            export = worker.root / 'comparison-events.jsonl'
            exports[day] = hashlib.sha256(export.read_bytes() if export.exists() else b'').hexdigest()
            health[day] = worker.health['initial_sync']
    replayed = sum(item['events'] for item in health.values())
    if replayed != len(events):
        raise ValueError('benchmark_requires_current_protocol_events_only')
    return {'replay_seconds': round(seconds, 6), 'events_replayed': replayed,
            'report_sha256': hashlib.sha256(canonical(reports).encode()).hexdigest(),
            'export_sha256_by_day': exports, 'sync_by_day': health}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--baseline-module', type=Path)
    parser.add_argument('--page-size', type=int, default=1000)
    args = parser.parse_args()
    if args.page_size < 1:
        parser.error('--page-size must be positive')
    opener = gzip.open if args.events.suffix == '.gz' else open
    with opener(args.events, 'rt') as source:
        events = [json.loads(line) for line in source if line.strip()]
    if not events:
        parser.error('--events must contain at least one event')
    result = {'scope': 'local_replay_only_excludes_network_and_report_generation',
              'source_file_sha256': hashlib.sha256(args.events.read_bytes()).hexdigest(),
              'event_counts': dict(Counter(event['kind'] for event in events)),
              'page_size': args.page_size}
    if args.baseline_module:
        result['baseline'] = measure(events, page_size=args.page_size,
                                     baseline_path=args.baseline_module)
    result['current'] = measure(events, page_size=args.page_size)
    if 'baseline' in result:
        before, after = result['baseline'], result['current']
        result['reports_identical'] = before['report_sha256'] == after['report_sha256']
        result['exports_identical'] = before['export_sha256_by_day'] == after['export_sha256_by_day']
        if not result['reports_identical'] or not result['exports_identical']:
            raise ValueError('replay_equivalence_failed')
        result['speedup'] = round(before['replay_seconds'] / after['replay_seconds'], 2)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
