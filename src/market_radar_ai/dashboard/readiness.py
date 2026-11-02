"""Acceptance report for a bounded live-data rehearsal, not trading readiness."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from .export import build_snapshot


def assess(document, *, now):
    snapshot = build_snapshot(document, now=now)
    checks = {f'{market}_has_current_data': snapshot['coverage'][market]['current'] > 0
              for market in ('stocks','crypto')}
    checks['all_attempts_current'] = all(
        c['attempted'] > 0 and c['current'] == c['attempted']
        for c in snapshot['coverage'].values())
    checks['no_trade_calls'] = all(row['decision']=='NO_ACTION'
        for rows in snapshot['markets'].values() for row in rows)
    return {'schema_version':1,'tested_at':now.isoformat(),
        'data_rehearsal_passed':all(checks.values()),'checks':checks,
        'trading_ready':False,'limitations':['Sample coverage only','No broker eligibility verified',
        'No connected news evidence','No real-market agent decision evaluated'],
        'coverage':snapshot['coverage']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=assess(json.loads(args.capture.read_text()),now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return int(not report['data_rehearsal_passed'])


if __name__=='__main__':
    raise SystemExit(main())
