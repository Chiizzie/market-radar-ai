"""One-share, bounded broker-paper plumbing exercise; not a strategy trade.

Requires an empty dedicated paper account, current IEX quote and existing indicative
FX adapter. It never runs from the scheduled scanner and cannot reach a live endpoint.
"""
import argparse
from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR
import json
from pathlib import Path
import time

from .alpaca import AlpacaPaper
from .cli import preflight, write_report
from .engine import Engine
from .journal import Journal
from .models import Intent, SafetyError, dec, instant, utcnow


def build_intent(broker, fx, exercise_id):
    clock = broker.clock()
    quote = broker.latest_quote("F")
    now = utcnow()
    entry = dec(quote["ap"]).quantize(dec("0.01"), rounding=ROUND_CEILING)
    if not dec("2") <= entry <= dec("30"):
        raise SafetyError("engineering exercise price outside $2-$30 bound")
    stop = (entry * dec("0.98")).quantize(dec("0.01"), rounding=ROUND_FLOOR)
    target = (entry * dec("1.02")).quantize(dec("0.01"), rounding=ROUND_CEILING)
    return Intent(exercise_id, exercise_id, "broker-paper-plumbing-v1", "F", "1", str(entry), str(stop),
                  str(target), str(quote["bp"]), str(quote["ap"]), str(dec(1) / fx.eur_per_unit),
                  now.isoformat(), quote["t"], fx.observed_at.isoformat(),
                  (now + timedelta(seconds=30)).isoformat(), clock["next_close"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-id", required=True)
    parser.add_argument("--paper-orders", action="store_true")
    parser.add_argument("--directory", default="artifacts/paper-exercise")
    parser.add_argument("--wait-for-open-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.paper_orders:
        parser.error("this exercise places paper orders; --paper-orders is required")
    if not 0 <= args.wait_for_open_seconds <= 3600:
        parser.error("wait-for-open-seconds must be between 0 and 3600")
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    journal, engine = None, None
    report = {"mode": "paper", "source": "broker_paper_engineering_exercise", "strategy_evaluation": False,
              "live_orders_enabled": False, "verification_complete": False}
    try:
        broker = AlpacaPaper.from_env()
        readiness = preflight(broker)
        report["preflight"] = readiness
        if readiness["open_order_count"] or readiness["position_count"]:
            raise SafetyError("exercise requires empty dedicated paper account")
        wait_deadline = time.monotonic() + args.wait_for_open_seconds
        while not readiness["market_open"]:
            if time.monotonic() >= wait_deadline:
                raise SafetyError("market closed; no queued or extended-hours exercise")
            report.update(waiting_for_regular_session=True, checked_at=utcnow().isoformat())
            write_report(directory / "report.json", report)
            time.sleep(min(30, max(0, wait_deadline - time.monotonic())))
            clock = broker.clock()
            readiness.update(market_open=clock["is_open"], next_close=clock["next_close"])
        report["waiting_for_regular_session"] = False
        if instant(readiness["next_close"]) - utcnow() < timedelta(minutes=15):
            raise SafetyError("insufficient regular session remaining")
        # Reuse the scanner's FX provider, including its completed-bar/freshness checks.
        from market_radar_ai.market_data.providers.fx import YahooFxProvider
        fx = YahooFxProvider().fetch("USD")
        journal = Journal(directory / "journal.sqlite3")
        engine = Engine(journal, broker)
        for attempt in range(3):
            plan = build_intent(broker, fx, args.exercise_id)
            # Refresh evidence only BEFORE any durable submission attempt exists.
            write_report(directory / f"intent-{attempt + 1}.json", plan.body())
            try:
                engine.submit(plan)
                break
            except SafetyError as exc:
                if journal.rows() or str(exc) != "stale or future evidence" or attempt == 2:
                    raise
        started = time.monotonic()
        protected_seen = False
        while time.monotonic() - started < 240:
            status = engine.tick()
            item = status["intents"][0]
            protected_seen |= item["state"] == "OPEN_PROTECTED"
            if item["state"] == "OPEN_PROTECTED" or time.monotonic() - started > 30:
                journal.request_exit(plan.intent_id, "bounded engineering exercise complete")
            report.update(engine=status, protection_observed=protected_seen,
                          checked_at=utcnow().isoformat(), fx_source=fx.source)
            write_report(directory / "report.json", report)
            if status["all_intents_terminal"]:
                final = preflight(broker)
                report["final_preflight"] = final
                report["verification_complete"] = (item["state"] == "CLOSED" and protected_seen
                    and not status["last_error"] and final["position_count"] == 0 and final["open_order_count"] == 0)
                break
            time.sleep(2)
        else:
            report["unresolved"] = "bounded exercise did not reconcile flat; restore journal and investigate"
        return 0 if report["verification_complete"] else 3
    except Exception as exc:
        # If the control process fails, preserve the journal and do not invent a clean exit.
        report["error_type"] = type(exc).__name__
        if isinstance(exc, SafetyError):
            report["error_code"] = str(exc)
        if engine:
            report["engine"] = engine.report()
        return 2
    finally:
        report["finished_at"] = utcnow().isoformat()
        write_report(directory / "report.json", report)
        if journal:
            journal.backup(directory / "recovery.sqlite3")
            journal.close()
        print(json.dumps(report))


if __name__ == "__main__":
    raise SystemExit(main())
