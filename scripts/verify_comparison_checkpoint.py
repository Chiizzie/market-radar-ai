"""Read-only production recovery proof; never requests market data or writes events."""
import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from market_radar_ai.agents.comparison_live import EventClient, LiveComparison
from market_radar_ai.agents.comparison_checkpoint import save, restore
from market_radar_ai.agents.candidate_packages import digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--day', required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path)
    a=p.parse_args()
    secret=os.environ['REVIEW_INGEST_SECRET'];client=EventClient(secret)
    now=datetime.now(UTC)
    with TemporaryDirectory() as temp:
        root=Path(temp)
        cold=LiveComparison(root/'cold',client=client,day=a.day)
        start=time.monotonic();cold.sync();cold_seconds=time.monotonic()-start
        if not cold.cursor:raise ValueError('no_history_to_verify')
        cache=a.checkpoint or root/'cache'
        save(cold,cache,secret)
        original_report=cold.store.report(now=now)
        original=(cold.root/'comparison-events.jsonl').read_bytes()
        warm=LiveComparison(root/'warm',client=client,day=a.day)
        start=time.monotonic()
        if not restore(warm,cache,secret):raise ValueError('checkpoint_restore_failed')
        restore_seconds=time.monotonic()-start
        assert warm.store.report(now=now)==original_report
        assert (warm.root/'comparison-events.jsonl').read_bytes()==original
        start=time.monotonic();warm.sync();tail_seconds=time.monotonic()-start
        assert warm.cursor>=cold.cursor
        # Independently replay the resulting raw history, including any new
        # server tail, through the uncached path and compare every report field.
        independent=LiveComparison(root/'independent',client=client,day=a.day)
        with independent.store.replay_batch():
            with (warm.root/'comparison-events.jsonl').open() as f:
                for line in f: independent.apply(json.loads(line))
        report=warm.store.report(now=now)
        assert independent.store.report(now=now)==report
        result={'schema_version':'checkpoint-recovery-verification-v1',
                'verified_at':datetime.now(UTC).isoformat(),'evaluation_day':a.day,
                'runtime_revision':os.environ.get('RUNTIME_REVISION'),
                'experiment_id':warm.experiment,'model_calls':0,'trade_authorized':False,
                'cold_events':len(cold.seen),'warm_events':len(warm.seen),
                'cold_cursor':cold.cursor,'warm_cursor':warm.cursor,
                'cold_seconds':round(cold_seconds,3),'restore_seconds':round(restore_seconds,3),
                'tail_seconds':round(tail_seconds,3),'tail_health':warm.health,
                'prefix_bytes':len(original),'prefix_sha256':hashlib.sha256(original).hexdigest(),
                'report_sha256':digest(report),'cohort_count':report['cohort_count'],
                'prefix_bytes_equal':True,'all_report_fields_equal':True,
                'limitations':['Read-only replay proof, not live quote-cadence or trading-performance validation.']}
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
