"""Bounded five-second paper quote watcher. No models and no order endpoints."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import time
from . import github_paper_tracking as journal
from .paper_observer import ReferenceObserver
from .watcher_diagnostics import record_failure
from ..dashboard.collection_schedule import scheduled_scope
from ..dashboard.paper_lifecycle_delivery import notify


def allowed(env, now):
    local=now.astimezone(ZoneInfo('Europe/Dublin'))
    return (scheduled_scope(env,now) and env.get('SCANNER_VERIFY_OUTSIDE_WINDOW')!='true'
            and local.weekday()<5 and 8<=local.hour<23)


def active_decisions(state, report, *, now):
    active={r['packet_id'] for r in report['trades'] if r['state'] in ('watching','open_simulation')}
    return [d for d in state['decisions'] if d['packet_id'] in active
            and now<=datetime.fromisoformat(d['plan']['exit_by'])]


def poll_once(*, env, observer, clock, session=None, notifications=True, state=None, seen=None):
    now=clock()
    if not allowed(env,now): raise ValueError('paper_watcher_scope_or_window')
    if any(env.get(k) for k in ('OPENAI_API_KEY','OPEN_API_KEY','GH_BUDGET_TOKEN')):
        raise ValueError('paid_credentials_forbidden_in_paper_watcher')
    token=env.get('GH_PAPER_TOKEN')
    if state is None: state,_=journal.load(token,session=session)
    before=journal.inspect(state,now=now)
    active=active_decisions(state,before,now=now)
    observations,failures=observer.fetch(active) if active else ([],[])
    # The journal's CAS merge reads the current head again if another worker won.
    updated,report=journal.apply(state,now=clock(),observations=observations)
    if updated!=state:
        journal.update(token,now=clock(),observations=observations,session=session)
        updated,_=journal.load(token,session=session)
        report=journal.inspect(updated,now=clock())
    receipt=notify(report,env=env,now=clock(),seen=seen,decisions=updated['decisions']) if notifications else {'sent':0,'unconfirmed':0}
    return {'active_plans':len(active),'quotes_received':len(observations),'failures':failures,
            'notifications':receipt,'report':report,'state':updated}


def run(*, env, output, duration=330, interval=5, clock=lambda:datetime.now(timezone.utc),
        monotonic=time.monotonic, sleep=time.sleep, observer=None, session=None):
    if not 1<=duration<=600 or not 1<=interval<=10: raise ValueError('bounded_watcher_required')
    if any(env.get(k) for k in ('OPENAI_API_KEY','OPEN_API_KEY','GH_BUDGET_TOKEN')):
        raise ValueError('paid_credentials_forbidden_in_paper_watcher')
    observer=observer or ReferenceObserver(env,clock=clock)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    status={'schema_version':'paper-watcher-health-v1','started_at':clock().isoformat(),
            'target_interval_seconds':interval,'polls':0,'quotes_received':0,'error_polls':0,
            'notification_unconfirmed':0,'maximum_poll_gap_seconds':0,'model_calls':0,
            'live_orders_enabled':False,'trade_authorized':False}
    end=monotonic()+duration; previous=None; state=None; refreshed=None; seen=set()
    while monotonic()<end and allowed(env,clock()):
        tick=monotonic()
        if previous is not None: status['maximum_poll_gap_seconds']=max(status['maximum_poll_gap_seconds'],round(tick-previous,3))
        previous=tick
        try:
            if state is None or refreshed is None or tick-refreshed>=15:
                state,_=journal.load(env.get('GH_PAPER_TOKEN'),session=session);refreshed=tick
            result=poll_once(env=env,observer=observer,clock=clock,session=session,state=state,seen=seen)
            state=result['state']
            status['polls']+=1;status['quotes_received']+=result['quotes_received']
            status['active_plans']=result['active_plans']
            status['last_success_at']=clock().isoformat()
            status['error_polls']+=bool(result['failures'])
            for failure in result['failures']: record_failure(status, failure, clock())
            status['notification_unconfirmed']+=result['notifications']['unconfirmed']
            (output/'paper-tracking.json').write_text(json.dumps(result['report'],indent=2)+'\n')
        except (RuntimeError,ValueError,KeyError,TypeError) as exc:
            status['error_polls']+=1  # Sanitized; provider bodies and credentials never reach logs.
            record_failure(status, exc, clock())
            state=None
            if str(exc)=='paper_journal_rate_limited':
                status['rate_limited']=True;break
        status['maximum_poll_duration_seconds']=max(status.get('maximum_poll_duration_seconds',0),round(monotonic()-tick,3))
        status['checked_at']=clock().isoformat()
        status['state']='observing_with_gaps' if status['error_polls'] else 'observing'
        (output/'watcher-health.json').write_text(json.dumps(status,indent=2)+'\n')
        remaining=end-monotonic()
        if remaining>0: sleep(min(remaining,max(0.1,interval-(monotonic()-tick))))
    status['state']='outside_window' if status['polls']==0 and status['error_polls']==0 else 'completed_with_gaps' if status['error_polls'] else 'completed'
    status['completed_at']=clock().isoformat()
    (output/'watcher-health.json').write_text(json.dumps(status,indent=2)+'\n')
    return status


def main():
    import argparse,os
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('artifacts/paper-watcher'))
    p.add_argument('--duration',type=int,default=330)
    args=p.parse_args()
    result=run(env=os.environ,output=args.output,duration=args.duration)
    print(json.dumps(result))
    return int(result['error_polls']>0 or result['notification_unconfirmed']>0)


if __name__=='__main__': raise SystemExit(main())
