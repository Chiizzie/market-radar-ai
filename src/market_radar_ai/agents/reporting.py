"""Read-only audit export for a future dashboard; no activation or trading controls."""
import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo


def export_run(store, run_id):
    record = store.inspect(run_id)
    request = record['request']
    result = record['result']
    debate = result['debate'] if result else None
    outcome = None
    with sqlite3.connect(store.path) as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_replays'").fetchone()
        if table:
            row = db.execute('SELECT payload FROM paper_replays WHERE run_id=?',(run_id,)).fetchone()
            if row: outcome = json.loads(row[0])['outcome']
    stamp = datetime.fromisoformat(request['now'])
    return {
        'schema_version': '1.0', 'run_id': run_id,
        'mode': 'SIMULATED_RESEARCH', 'state': record['state'],
        'symbol': request['snapshot']['symbol'],
        'as_of_dublin': stamp.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
        'currency': 'EUR',
        'reports': debate['reports'] if debate else [],
        'objections': debate['objections'] if debate else [],
        'rebuttals': debate['rebuttals'] if debate else [],
        'decision': debate['final'] if debate else None,
        'accepted_plan': result['plan'] if result else None,
        'paper_outcome': outcome,
        'failure': record['failure'],
        'agent_accuracy': None,
        'limitations': ['Simulated model responses; no live orders.',
                        'Paper fills are quote-replay assumptions, not broker executions.',
                        'No measured agent accuracy is available.'],
    }


def outcome_summary(store):
    """Summarize recorded replay outcomes only, excluding unresolved P&L."""
    from decimal import Decimal
    with sqlite3.connect(store.path) as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_replays'").fetchone()
        rows = db.execute('SELECT payload FROM paper_replays').fetchall() if table else []
    outcomes = [json.loads(row[0])['outcome'] for row in rows]
    closed = [o for o in outcomes if o['status']=='closed']
    pnls = [Decimal(o['net_pnl_eur']) for o in closed]
    return {'mode':'SIMULATED_RESEARCH', 'recorded_replays':len(outcomes),
            'closed':len(closed), 'unresolved':sum(o['status']=='unresolved' for o in outcomes),
            'not_filled':sum(o['status']=='not_filled' for o in outcomes),
            'net_pnl_eur':str(sum(pnls,Decimal(0))) if pnls else None,
            'profitable_closed_fraction':sum(p>0 for p in pnls)/len(pnls) if pnls else None,
            'agent_accuracy':None}


def main():
    import argparse
    from .debate_store import DebateStore
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--run-id')
    args=parser.parse_args()
    from pathlib import Path
    if not Path(args.database).is_file(): parser.error('Existing audit database required')
    store=DebateStore(args.database)
    print(json.dumps(export_run(store,args.run_id) if args.run_id else outcome_summary(store),indent=2))


if __name__=='__main__': main()
