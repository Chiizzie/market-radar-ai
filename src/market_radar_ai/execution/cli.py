"""Paper preflight, durable worker and read-only status export. No AI dependency."""
import argparse
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import time

from .alpaca import AlpacaPaper, BrokerError, PAPER_URL
from .engine import Engine
from .journal import Journal
from .models import Intent, SafetyError, utcnow


def write_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def preflight(broker):
    account, clock = broker.account(), broker.clock()
    orders, positions = broker.open_orders(), broker.positions()
    return {"schema": "broker-paper-preflight-v1", "checked_at": utcnow().isoformat(),
            "endpoint": PAPER_URL, "mode": "paper", "orders_submitted": 0,
            "account_status": account.get("status"), "account_currency": account.get("currency"),
            "trading_blocked": account.get("trading_blocked"), "account_blocked": account.get("account_blocked"),
            "trade_suspended_by_user": account.get("trade_suspended_by_user"),
            "open_order_count": len(orders), "position_count": len(positions),
            "market_open": clock.get("is_open"), "next_open": clock.get("next_open"),
            "next_close": clock.get("next_close"), "live_orders_enabled": False,
            "order_submission_permissions": "not_tested_by_read_only_preflight"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "run", "watch", "status", "backup"))
    parser.add_argument("--db", default="var/paper-execution/journal.sqlite3")
    parser.add_argument("--report", default="var/paper-execution/status.json")
    parser.add_argument("--intent")
    parser.add_argument("--paper-orders", action="store_true")
    parser.add_argument("--kill-file", default="var/paper-execution/STOP_ENTRIES")
    parser.add_argument("--flatten-file", default="var/paper-execution/FLATTEN")
    parser.add_argument("--backup-to")
    args = parser.parse_args(argv)
    if args.command == "status":
        # Reading status cannot send requests or acquire the worker's write lock.
        print(Path(args.report).read_text())
        return 0
    if args.command in {"run", "watch"} and not args.paper_orders:
        parser.error("run/watch can mutate only the paper account; specify --paper-orders")
    if args.command == "run" and not args.intent:
        parser.error("run requires --intent")
    journal = None
    engine = None
    try:
        if args.command == "preflight":
            report = preflight(AlpacaPaper.from_env())
            write_report(args.report, report)
            print(json.dumps(report))
            return 0
        journal = Journal(args.db)
        if args.command == "backup":
            if not args.backup_to:
                parser.error("backup requires --backup-to; stop the worker first")
            journal.backup(args.backup_to)
            return 0
        engine = Engine(journal, AlpacaPaper.from_env())
        stopping_at = None

        def stop(signum, frame):
            nonlocal stopping_at
            stopping_at = stopping_at or time.monotonic()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        # Resume first. Intent identity and reservations survive a worker restart.
        engine.tick()
        if args.intent:
            engine.submit(Intent(**json.loads(Path(args.intent).read_text())))
        while True:
            if Path(args.kill_file).exists():
                journal.halt("operator entry kill file")
            if stopping_at is not None or Path(args.flatten_file).exists():
                journal.halt("operator requested paper flatten")
                for row in journal.rows(active=True):
                    journal.request_exit(row["id"], "operator shutdown/flatten")
            report = engine.tick()
            report["generated_at"] = utcnow().isoformat()
            write_report(args.report, report)
            if report["all_intents_terminal"] and (args.command == "run" or stopping_at is not None):
                return 0 if not report["last_error"] else 2
            if stopping_at is not None and time.monotonic() - stopping_at >= 120:
                # Never claim flat when a halt, rejected exit or missing response prevents proof.
                return 3
            time.sleep(2)
    except (SafetyError, BrokerError, sqlite3.Error, ValueError, TypeError, OSError) as exc:
        report = engine.report() if engine else {"mode": "paper", "live_orders_enabled": False}
        report.update(error_type=type(exc).__name__, verification_complete=False)
        # Avoid raw exception payloads: broker/account data must not leak into public logs.
        write_report(args.report, report)
        print(json.dumps({"error_type": type(exc).__name__, "report": args.report}), file=sys.stderr)
        return 2
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
