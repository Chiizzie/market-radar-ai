"""Independent comparison worker: storage replay cannot delay approved quotes."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from .comparison_live import EventClient, LiveComparison
from .paper_observer import ReferenceObserver
from .paper_watcher import allowed
from .watcher_diagnostics import record_failure, recovered_quote_gaps


def run(*, env, output, duration=330, interval=5, clock=lambda: datetime.now(timezone.utc),
        monotonic=time.monotonic, sleep=time.sleep, factory=None):
    if not 1 <= duration <= 600 or not 1 <= interval <= 10:
        raise ValueError('bounded_watcher_required')
    if any(env.get(k) for k in ('OPENAI_API_KEY','OPEN_API_KEY','GH_BUDGET_TOKEN')):
        raise ValueError('paid_credentials_forbidden_in_comparison_watcher')
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    health={'polls':0,'quotes_received':0,'error_polls':0,'model_calls':0,
            'started_at':clock().isoformat(),'maximum_poll_duration_seconds':0,
            'maximum_poll_gap_seconds':0,'trade_authorized':False}
    start=monotonic(); end=start+duration; previous=None; comparison=None
    try:
        if allowed(env,clock()):
            comparison=(factory or (lambda: LiveComparison(output,
                client=EventClient(env.get('REVIEW_INGEST_SECRET'),clock=clock),
                observer=ReferenceObserver(env,clock=clock),clock=clock)))()
            # Restore immutable history before measuring the steady quote cadence.
            # Startup remains separately timed; it never counts as a quote or a
            # recovered data gap, and cannot consume the whole worker window.
            health['startup_state']='restoring'
            try:
                if env.get('RESEARCH_CHECKPOINT_DIR'):
                    from .comparison_checkpoint import restore
                    restore(comparison, env['RESEARCH_CHECKPOINT_DIR'], env.get('REVIEW_INGEST_SECRET'))
                comparison.sync()
            except (RuntimeError,ValueError,KeyError,TypeError):
                health['startup_state']='failed'
                raise
            finally:
                health['startup_sync_seconds']=monotonic()-start
                health['comparison']=dict(comparison.health)
            health['startup_state']='slow' if health['startup_sync_seconds']>15 else 'ready'
            if health['startup_sync_seconds']>15: health['requires_attention']=True
            if monotonic()>=end:
                health['startup_state']='window_exhausted'
                raise RuntimeError('comparison_startup_deadline_exceeded')
        while comparison is not None and monotonic()<end and allowed(env,clock()):
            tick=monotonic()
            if previous is not None:
                health['maximum_poll_gap_seconds']=max(health['maximum_poll_gap_seconds'],tick-previous)
            previous=tick
            try:
                comparison.poll()
                health['polls']=comparison.health['polls']
                health['quotes_received']=comparison.health['quotes_received']
                health.setdefault('first_completed_poll_delay_seconds',monotonic()-start)
            except (RuntimeError,ValueError,KeyError,TypeError) as exc:
                comparison.health['error_polls']+=1
                record_failure(comparison.health,exc,clock())
            health['comparison']=dict(comparison.health)
            health['error_polls']=comparison.health['error_polls']
            health['maximum_poll_duration_seconds']=max(health['maximum_poll_duration_seconds'],monotonic()-tick)
            (output/'worker-health.json').write_text(json.dumps(health,indent=2)+'\n')
            remaining=end-monotonic()
            if remaining>0: sleep(min(remaining,max(.1,interval-(monotonic()-tick))))
        if comparison is not None:
            comparison.close()
            if env.get('RESEARCH_CHECKPOINT_DIR'):
                from .comparison_checkpoint import save
                save(comparison, env['RESEARCH_CHECKPOINT_DIR'], env.get('REVIEW_INGEST_SECRET'))
    except (RuntimeError,ValueError,KeyError,TypeError) as exc:
        health['error_polls']+=1; record_failure(health,exc,clock())
    health['completed_at']=clock().isoformat()
    health['state']='completed_with_gaps' if health['error_polls'] else 'completed' if comparison else 'outside_window'
    health['critical_failure']=bool(health['error_polls'])
    if recovered_quote_gaps(health):
        health['state']='completed_with_recovered_quote_gaps'
        health['critical_failure']=False
        health['requires_attention']=True
    (output/'worker-health.json').write_text(json.dumps(health,indent=2)+'\n')
    return health


def main():
    import argparse,os
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('artifacts/paper-watcher/comparison'))
    p.add_argument('--duration',type=int,default=330)
    args=p.parse_args(); result=run(env=os.environ,output=args.output,duration=args.duration)
    print(json.dumps(result))
    if result.get('requires_attention'):
        print('::warning::Comparison has startup or recovered-quote warnings; inspect worker-health.json for retained timings and gaps.')
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
                f.write('\n- Comparison warnings: startup '+str(result.get('startup_sync_seconds'))
                    +' seconds; recovered gaps '+json.dumps(result.get('comparison',{}).get('quote_gap_counts',{}))
                    +'. Historical gaps remain recorded.\n')
    return int(result['critical_failure'])

if __name__=='__main__': raise SystemExit(main())
