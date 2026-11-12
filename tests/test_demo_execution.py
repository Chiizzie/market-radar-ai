"""Fault injection for broker-paper execution. These are not broker fills or alpha tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import random
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

from market_radar_ai.execution.alpaca import AlpacaPaper, BrokerError, PAPER_URL
from market_radar_ai.execution.engine import Engine, ORDER_TERMINAL
from market_radar_ai.execution.journal import Journal
from market_radar_ai.execution.models import Intent, Limits, SafetyError, dec

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
CLOSE = NOW.replace(hour=21)


def intent(**changes):
    result = Intent("test-source-1", "source-event-123", "engineering-fixture-v1", "TEST", "4",
                    "100.00", "98.00", "104.00", "99.98", "100.00", "1.10",
                    NOW.isoformat(), NOW.isoformat(), NOW.isoformat(),
                    (NOW + timedelta(seconds=60)).isoformat(), CLOSE.isoformat())
    return replace(result, **changes)


class Broker:
    def __init__(self):
        self.now = NOW
        self.orders = {}
        self.posts = []
        self.cancels = []
        self.account_id = "synthetic-paper-account"
        self.post_fault = None
        self.lookup_missing = False
        self.read_fault = False
        self.cancel_fault = False
        self.cancel_pending = False
        self.cancel_fill_race = None
        self.extra_positions = []
        self.open = True
        self.cash = "100000"
        self.blocked = False

    def account(self):
        if self.read_fault:
            raise BrokerError()
        return {"id": self.account_id, "currency": "USD", "status": "ACTIVE", "cash": self.cash,
                "trading_blocked": self.blocked, "account_blocked": False, "trade_suspended_by_user": False}

    def clock(self):
        return {"timestamp": self.now.isoformat(), "is_open": self.open, "next_close": CLOSE.isoformat()}

    def submit(self, payload):
        if payload["side"] == "sell":
            actual_position = sum((dec(o["filled_qty"]) * (1 if o["side"] == "buy" else -1)
                                   for o in self.orders.values() if o["symbol"] == payload["symbol"]), dec(0))
            assert 0 < dec(payload["qty"]) <= actual_position, "engine attempted to sell more than owned"
            assert all(o["status"] in ORDER_TERMINAL for o in self.orders.values()
                       if o["symbol"] == payload["symbol"]), "engine submitted exit before cancel completion"
        self.posts.append(deepcopy(payload))
        if self.post_fault == "before_accept":
            raise BrokerError()
        order = dict(payload, id=f"order-{len(self.posts)}", status="new", filled_qty="0", filled_avg_price=None)
        self.orders[order["id"]] = order
        if payload.get("order_class") == "bracket":
            order["leg_ids"] = []
            for name, kind, price in (("tp", "limit", "limit_price"), ("sl", "stop", "stop_price")):
                leg = {"id": order["id"] + "-" + name, "client_order_id": "broker-" + order["id"] + name,
                       "symbol": order["symbol"], "side": "sell", "qty": order["qty"], "type": kind,
                       "status": "held", "filled_qty": "0", "filled_avg_price": None,
                       price: payload["take_profit" if name == "tp" else "stop_loss"][price]}
                self.orders[leg["id"]] = leg
                order["leg_ids"].append(leg["id"])
        if self.post_fault == "after_accept":
            raise BrokerError()
        return self.get_order(order["id"])

    def lookup(self, cid):
        if self.lookup_missing:
            return None
        return next((self.get_order(o["id"]) for o in self.orders.values() if o["client_order_id"] == cid), None)

    def get_order(self, order_id):
        order = deepcopy(self.orders[order_id])
        order["legs"] = [deepcopy(self.orders[leg]) for leg in order.pop("leg_ids", [])]
        return order

    def open_orders(self):
        return [self.get_order(o["id"]) for o in self.orders.values() if o["status"] not in ORDER_TERMINAL]

    def positions(self):
        symbols = {}
        for o in self.orders.values():
            symbols[o["symbol"]] = symbols.get(o["symbol"], dec(0)) + dec(o["filled_qty"]) * (1 if o["side"] == "buy" else -1)
        return [{"symbol": s, "qty": str(q)} for s, q in symbols.items() if q] + self.extra_positions

    def fill(self, order_id, qty, price):
        order = self.orders[order_id]
        order.update(filled_qty=str(qty), filled_avg_price=str(price),
                     status="filled" if dec(qty) == dec(order["qty"]) else "partially_filled")
        if order.get("leg_ids") and order["status"] == "filled":
            for leg in order["leg_ids"]:
                self.orders[leg]["status"] = "new"

    def cancel(self, order_id):
        self.cancels.append(order_id)
        order = self.orders[order_id]
        if self.cancel_fill_race == order_id:
            self.fill(order_id, order["qty"], "99")
            self.cancel_fill_race = None
            return
        if self.cancel_fault:
            raise BrokerError()
        if order["status"] not in ORDER_TERMINAL:
            order["status"] = "pending_cancel" if self.cancel_pending else "canceled"


class DemoEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "journal.sqlite3"
        self.journal = Journal(self.path)
        self.broker = Broker()
        self.engine = Engine(self.journal, self.broker)

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def start(self, **changes):
        plan = intent(**changes)
        self.engine.submit(plan, NOW)
        return plan

    def tick(self, now=NOW):
        self.broker.now = now
        return self.engine.tick(now)

    def filled(self):
        plan = self.start()
        self.broker.fill("order-1", 4, 100)
        self.tick()
        return plan

    def state(self):
        return self.journal.get("test-source-1")["state"]

    def test_full_entry_protection_exit_and_pnl(self):
        self.filled()
        self.assertEqual(self.state(), "OPEN_PROTECTED")
        self.broker.fill("order-1-tp", 4, 104)
        self.broker.orders["order-1-sl"]["status"] = "canceled"
        report = self.tick()
        self.assertEqual(self.state(), "CLOSED")
        self.assertEqual(report["intents"][0]["remaining_from_fills"], "0")
        self.assertEqual(dec(report["intents"][0]["pnl_eur_after_assumed_costs"]), Decimal("14.4") / Decimal("1.1"))
        self.assertEqual(len(self.broker.posts), 1)
        self.assertFalse(report["fees_verified"])

    def test_ack_is_not_fill(self):
        self.start()
        self.tick()
        self.assertEqual(self.state(), "ENTRY_WORKING")
        self.assertFalse(self.engine.report()["intents"][0]["protection_observed"])

    def test_duplicate_signal_posts_once(self):
        plan = self.start()
        for _ in range(4):
            self.engine.submit(plan, NOW)
        self.assertEqual(len(self.broker.posts), 1)

    def test_changed_duplicate_rejected(self):
        plan = self.start()
        with self.assertRaises(SafetyError):
            self.engine.submit(replace(plan, stop_usd="97.00"), NOW)
        self.assertEqual(len(self.broker.posts), 1)

    def test_same_source_with_new_id_cannot_reenter_after_close(self):
        plan = self.filled()
        self.broker.fill("order-1-tp", 4, 104)
        self.broker.orders["order-1-sl"]["status"] = "canceled"
        self.tick()
        with self.assertRaisesRegex(SafetyError, "source event already consumed"):
            self.engine.submit(replace(plan, intent_id="changed-id"), NOW)
        self.assertEqual(len(self.broker.posts), 1)

    def test_timeout_after_accept_reconciles_without_resubmit(self):
        self.broker.post_fault = "after_accept"
        plan = self.start()
        self.assertEqual(self.state(), "SUBMISSION_UNKNOWN")
        self.broker.post_fault = None
        self.broker.fill("order-1", 4, 100)
        self.engine.submit(plan, NOW)
        self.assertEqual(self.state(), "OPEN_PROTECTED")
        self.assertEqual(len(self.broker.posts), 1)
        self.assertTrue(self.journal.get_meta("entry_halt"))

    def test_timeout_before_accept_and_404_never_blind_retry(self):
        self.broker.post_fault = "before_accept"
        plan = self.start()
        self.broker.post_fault = None
        for _ in range(3):
            self.engine.submit(plan, NOW)
        self.assertEqual(self.state(), "RECONCILIATION_REQUIRED")
        self.assertEqual(len(self.broker.posts), 1)
        self.assertEqual(len(self.journal.rows(active=True)), 1)

    def test_partial_entry_cancel_then_flatten_only_filled_qty(self):
        self.start()
        self.broker.fill("order-1", 1, 100)
        report = self.tick()
        self.assertFalse(report["intents"][0]["protection_observed"])
        self.assertEqual(self.state(), "EXIT_CANCEL_PENDING")
        self.assertEqual(len(self.broker.posts), 1)
        self.tick()
        self.assertEqual(self.broker.posts[-1]["qty"], "1")
        self.assertEqual(self.broker.posts[-1]["side"], "sell")
        self.broker.fill("order-2", 1, 99)
        self.tick()
        self.assertEqual(self.state(), "CLOSED")

    def test_partial_fill_during_entry_cancel_uses_final_quantity(self):
        self.start()
        self.broker.fill("order-1", 1, 100)
        self.broker.cancel_fill_race = "order-1"
        self.tick()
        self.tick()
        self.assertEqual(self.broker.posts[-1]["qty"], "4")

    def test_cancel_ack_does_not_authorize_flatten(self):
        self.start()
        self.broker.fill("order-1", 1, 100)
        self.broker.cancel_pending = True
        for _ in range(3):
            self.tick()
        self.assertEqual(len(self.broker.posts), 1)
        self.assertEqual(self.state(), "EXIT_CANCEL_PENDING")

    def test_cancel_timeout_does_not_authorize_flatten(self):
        self.filled()
        self.journal.request_exit("test-source-1", "test exit")
        self.broker.cancel_fault = True
        for _ in range(2):
            self.tick()
        self.assertEqual(len(self.broker.posts), 1)
        self.assertTrue(self.journal.get_meta("entry_halt"))

    def test_stop_fills_during_cancel_no_duplicate_sell(self):
        self.filled()
        self.journal.request_exit("test-source-1", "test exit")
        self.broker.cancel_fill_race = "order-1-sl"
        self.tick()
        self.tick()
        self.assertEqual(len(self.broker.posts), 1)
        self.assertEqual(self.state(), "CLOSED")

    def test_protection_rejection_triggers_visible_recovery(self):
        self.filled()
        self.broker.orders["order-1-sl"]["status"] = "rejected"
        self.tick()
        self.assertIn("protective stop", self.journal.get_meta("entry_halt"))
        self.tick()
        self.assertEqual(len(self.broker.posts), 2)
        self.assertEqual(self.broker.posts[-1]["qty"], "4")

    def test_protection_wrong_quantity_triggers_recovery(self):
        self.filled()
        self.broker.orders["order-1-sl"]["qty"] = "3"
        self.tick()
        self.assertEqual(self.state(), "EXIT_CANCEL_PENDING")

    def test_partial_target_adjusted_stop_remains_protected(self):
        self.filled()
        self.broker.fill("order-1-tp", 1, 104)
        self.broker.orders["order-1-sl"]["qty"] = "3"
        self.tick()
        self.assertEqual(self.state(), "OPEN_PROTECTED")
        self.assertEqual(len(self.broker.posts), 1)

    def test_partial_exit_waits_then_closed(self):
        self.filled()
        self.journal.request_exit("test-source-1", "test exit")
        self.tick()
        self.tick()
        self.broker.fill("order-2", 1, 99)
        for _ in range(3):
            self.tick()
        self.assertEqual(len(self.broker.posts), 2)
        self.broker.fill("order-2", 4, 99)
        self.tick()
        self.assertEqual(self.state(), "CLOSED")

    def test_canceled_partial_exit_retries_only_remainder(self):
        self.filled()
        self.journal.request_exit("test-source-1", "test exit")
        self.tick()
        self.tick()
        self.broker.fill("order-2", 1, 99)
        self.broker.orders["order-2"]["status"] = "canceled"
        self.tick()
        self.assertEqual(self.broker.posts[-1]["qty"], "3")
        self.assertEqual(len({p["client_order_id"] for p in self.broker.posts}), 3)

    def test_unknown_exit_is_not_duplicated(self):
        self.filled()
        self.journal.request_exit("test-source-1", "test exit")
        self.tick()
        self.broker.post_fault = "before_accept"
        self.tick()
        for _ in range(3):
            self.tick()
        self.assertEqual(len(self.broker.posts), 2)
        self.assertEqual(self.state(), "RECONCILIATION_REQUIRED")

    def test_restart_does_not_resubmit_entry(self):
        plan = self.filled()
        self.journal.close()
        self.journal = Journal(self.path)
        self.engine = Engine(self.journal, self.broker)
        self.engine.submit(plan, NOW)
        self.assertEqual(len(self.broker.posts), 1)
        self.assertEqual(self.state(), "OPEN_PROTECTED")

    def test_backup_restore_preserves_unknown_submission(self):
        self.broker.post_fault = "after_accept"
        plan = self.start()
        backup = Path(self.tmp.name) / "backup.sqlite3"
        self.journal.backup(backup)
        self.journal.close()
        self.journal = Journal(backup)
        self.engine = Engine(self.journal, self.broker)
        self.engine.submit(plan, NOW)
        self.assertEqual(len(self.broker.posts), 1)

    def test_crash_after_post_before_recording_ack_recovers(self):
        original_observe = self.journal.observe
        self.journal.observe = lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("disk full"))
        with self.assertRaises(sqlite3.OperationalError):
            self.start()
        self.journal.observe = original_observe
        self.journal.close()
        self.journal = Journal(self.path)
        self.engine = Engine(self.journal, self.broker)
        self.broker.fill("order-1", 4, 100)
        self.engine.submit(intent(), NOW)
        self.assertEqual(len(self.broker.posts), 1)
        self.assertEqual(self.state(), "OPEN_PROTECTED")

    def test_unknown_reservation_survives_day_boundary(self):
        self.broker.post_fault = "before_accept"
        self.start()
        self.tick(NOW + timedelta(days=1))
        self.assertEqual(len(self.journal.rows(active=True)), 1)
        self.assertGreater(dec(self.journal.rows(active=True)[0]["risk"]), 0)

    def test_foreign_unrelated_exposure_does_not_disable_our_exit(self):
        self.filled()
        self.broker.extra_positions = [{"symbol": "OTHER", "qty": "1"}]
        self.journal.request_exit("test-source-1", "test exit")
        self.tick()
        self.tick()
        self.assertEqual(self.broker.posts[-1]["symbol"], "TEST")
        self.assertEqual(self.broker.posts[-1]["qty"], "4")

    def test_exit_rejections_are_bounded(self):
        self.filled()
        self.journal.request_exit("test-source-1", "test exit")
        self.tick()
        for number in range(2, 5):
            self.tick()
            self.broker.orders[f"order-{number}"]["status"] = "rejected"
        self.tick()
        self.assertEqual(self.state(), "UNRESOLVED_EXIT_RETRIES")
        self.assertEqual(len(self.broker.posts), 4)  # Entry + at most 3 terminal exit attempts.

    def test_early_close_uses_broker_session(self):
        early_close = NOW + timedelta(minutes=5)
        self.broker.clock = lambda: {"timestamp": NOW.isoformat(), "is_open": True,
                                    "next_close": early_close.isoformat()}
        with self.assertRaises(SafetyError):
            self.start(session_close=early_close.isoformat())
        self.assertEqual(self.broker.posts, [])

    def test_second_writer_rejected(self):
        with self.assertRaises(SafetyError):
            Journal(self.path)

    def test_database_write_failure_prevents_post(self):
        self.journal.reserve = lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("disk full"))
        with self.assertRaises(sqlite3.OperationalError):
            self.start()
        self.assertEqual(self.broker.posts, [])
        self.assertEqual(self.journal.rows(), [])

    def test_broker_outage_halts_entries_retains_protection(self):
        self.filled()
        self.broker.read_fault = True
        self.tick()
        self.assertTrue(self.engine.last_error)
        self.assertEqual(self.broker.cancels, [])
        self.broker.read_fault = False
        self.tick()
        self.assertEqual(self.state(), "OPEN_PROTECTED")
        self.assertTrue(self.journal.get_meta("entry_halt"))

    def test_account_binding_rejects_changed_credentials(self):
        self.filled()
        self.broker.account_id = "different-account"
        self.tick()
        self.assertIn("different paper account", self.engine.last_error)
        self.assertEqual(self.broker.cancels, [])

    def test_foreign_position_blocks_entry_without_liquidation(self):
        self.broker.extra_positions = [{"symbol": "OTHER", "qty": "1"}]
        with self.assertRaises(SafetyError):
            self.start()
        self.assertEqual(self.broker.posts, [])
        self.assertEqual(self.broker.cancels, [])

    def test_position_mismatch_no_guessed_exit(self):
        self.filled()
        self.broker.positions = lambda: [{"symbol": "TEST", "qty": "2"}]
        self.journal.request_exit("test-source-1", "test exit")
        self.tick()
        self.assertEqual(self.state(), "RECONCILIATION_REQUIRED")
        self.assertEqual(len(self.broker.posts), 1)
        self.assertEqual(self.broker.cancels, [])

    def test_expired_unfilled_entry_canceled(self):
        self.start()
        self.tick(NOW + timedelta(seconds=61))
        self.tick(NOW + timedelta(seconds=62))
        self.assertEqual(self.state(), "CANCELED")

    def test_session_deadline_flattens_and_reconciles(self):
        self.filled()
        cutoff = CLOSE - timedelta(seconds=300)
        self.tick(cutoff)
        self.tick(cutoff + timedelta(seconds=1))
        self.assertEqual(self.broker.posts[-1]["side"], "sell")
        self.broker.fill("order-2", 4, 101)
        self.tick(cutoff + timedelta(seconds=2))
        self.assertEqual(self.state(), "CLOSED")

    def test_closed_session_never_queues_next_day_exit(self):
        self.filled()
        self.broker.open = False
        self.tick(CLOSE + timedelta(seconds=1))
        self.assertEqual(self.state(), "UNRESOLVED_SESSION_CLOSED")
        self.assertEqual(len(self.broker.posts), 1)
        self.assertEqual(self.broker.cancels, [])

    def test_entry_kill_does_not_cancel_existing_protection(self):
        self.filled()
        self.journal.halt("operator entry kill")
        self.tick()
        self.assertEqual(self.state(), "OPEN_PROTECTED")
        self.assertEqual(self.broker.cancels, [])

    def test_stale_feed_blocks_entry(self):
        with self.assertRaises(SafetyError):
            self.start(quote_at=(NOW - timedelta(seconds=6)).isoformat())
        self.assertEqual(self.broker.posts, [])

    def test_invalid_inputs_never_submit(self):
        for changes in ({"qty": "0"}, {"qty": "1.5"}, {"qty": "NaN"}, {"qty": "Infinity"},
                        {"usd_per_eur": "0"}, {"usd_per_eur": "NaN"}, {"mode": "live"},
                        {"stop_usd": "101.00"}, {"limit_usd": "100.001"}, {"source_event_id": ""},
                        {"quote_at": "2026-11-12T15:00:00"}, {"bid_usd": "95"},
                        {"expires_at": NOW.isoformat()}, {"symbol": "../bad"},
                        {"session_close": (CLOSE + timedelta(days=1)).isoformat()}):
            with self.subTest(changes=changes), self.assertRaises(SafetyError):
                self.start(**changes)
        self.assertEqual(self.broker.posts, [])

    def test_per_trade_risk_limit(self):
        with self.assertRaises(SafetyError):
            self.start(stop_usd="90.00")
        self.assertEqual(self.broker.posts, [])

    def test_combined_and_daily_risk_limits(self):
        self.engine.limits = replace(Limits(), combined_risk_eur=dec("10"))
        self.start()
        with self.assertRaisesRegex(SafetyError, "combined risk"):
            self.start(intent_id="second", symbol="TWO", source_event_id="event-2")
        self.assertEqual(len(self.broker.posts), 1)

    def test_daily_realized_loss_plus_reservation_limit(self):
        self.filled()
        self.broker.fill("order-1-sl", 4, 89)
        self.broker.orders["order-1-tp"]["status"] = "canceled"
        self.tick()
        with self.assertRaisesRegex(SafetyError, "daily loss"):
            self.start(intent_id="second", symbol="TWO", source_event_id="event-2")

    def test_cash_gate_does_not_use_margin(self):
        self.broker.cash = "10"
        with self.assertRaisesRegex(SafetyError, "cash"):
            self.start()

    def test_broker_blocked_account_cannot_submit(self):
        self.broker.blocked = True
        with self.assertRaises(SafetyError):
            self.start()
        self.assertEqual(self.broker.posts, [])

    def test_live_and_similar_hosts_rejected(self):
        for host in ("https://api.alpaca.markets", PAPER_URL + ".evil.test", PAPER_URL + "/", "http://paper-api.alpaca.markets"):
            with self.subTest(host=host), self.assertRaises(SafetyError):
                AlpacaPaper("fake", "fake", host)

    def test_repeated_observations_do_not_duplicate_fills(self):
        self.filled()
        count = self.journal.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        for _ in range(3):
            self.tick()
        self.assertEqual(self.journal.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], count)
        self.assertEqual(self.engine.report()["intents"][0]["remaining_from_fills"], "4")

    def test_regressing_fill_is_reconciliation_error(self):
        self.filled()
        self.broker.orders["order-1"]["filled_qty"] = "3"
        self.tick()
        self.assertIn("backwards", self.engine.last_error)

    def test_empty_journal_cannot_replay_completed_broker_intent(self):
        self.filled()
        self.broker.fill("order-1-tp", 4, 104)
        self.broker.orders["order-1-sl"]["status"] = "canceled"
        self.tick()
        self.journal.close()
        self.journal = Journal(Path(self.tmp.name) / "new.sqlite3")
        self.engine = Engine(self.journal, self.broker)
        with self.assertRaisesRegex(SafetyError, "outside journal"):
            self.engine.submit(intent(), NOW)
        self.assertEqual(len(self.broker.posts), 1)

    def test_backup_works_while_worker_owns_journal(self):
        from market_radar_ai.execution.cli import main
        self.filled()
        backup = Path(self.tmp.name) / "online.sqlite3"
        result = main(["backup", "--db", str(self.path), "--backup-to", str(backup)])
        self.assertEqual(result, 0)
        with sqlite3.connect(backup) as restored:
            self.assertEqual(restored.execute("SELECT state FROM intents").fetchone()[0], "OPEN_PROTECTED")
        self.assertEqual(len(self.broker.posts), 1)

    def test_transport_timeout_never_retries_post_or_leaks_secret(self):
        broker = AlpacaPaper("test-key", "secret-that-must-not-leak")
        with patch.object(broker._opener, "open", side_effect=TimeoutError("secret-that-must-not-leak")) as call:
            with self.assertRaises(BrokerError) as error:
                broker.submit(intent().entry_order())
            self.assertEqual(call.call_count, 1)
            self.assertNotIn("secret-that-must-not-leak", str(error.exception))
            self.assertEqual(call.call_args.args[0].full_url, PAPER_URL + "/v2/orders")

    def test_quote_host_cannot_be_used_for_order_mutation(self):
        broker = AlpacaPaper("test-key", "test-secret")
        for url, method in (("https://api.alpaca.markets/v2/orders", "GET"),
                            ("https://data.alpaca.markets/v2/orders", "POST"),
                            ("https://paper-api.alpaca.markets.evil.test/v2/orders", "POST")):
            with self.subTest(url=url), self.assertRaises(SafetyError):
                broker._http(method, url)

    def test_broker_oco_double_fill_is_unresolved_not_a_clean_close(self):
        self.filled()
        self.broker.fill("order-1-tp", 4, 104)
        self.broker.fill("order-1-sl", 4, 98)
        report = self.tick()
        self.assertEqual(self.state(), "RECONCILIATION_REQUIRED")
        self.assertFalse(report["all_intents_terminal"])
        self.assertEqual(len(self.broker.posts), 1)

    def test_corrupted_intent_fails_closed_with_visible_report(self):
        self.filled()
        row = self.journal.get("test-source-1")
        body = json.loads(row["body"])
        body["qty"] = "400"
        self.journal.db.execute("UPDATE intents SET body=? WHERE id=?", (json.dumps(body), row["id"]))
        report = self.tick()
        self.assertIn("fingerprint", report["last_error"])
        self.assertEqual(report["intents"][0]["state"], "JOURNAL_CORRUPT")
        self.assertFalse(report["all_intents_terminal"])
        self.assertEqual(self.broker.cancels, [])

    def test_engineering_fixture_has_bounded_notional_and_valid_current_evidence(self):
        from market_radar_ai.execution.exercise import build_intent
        self.broker.latest_quote = lambda symbol: {"t": NOW.isoformat(), "bp": "12.00", "ap": "12.01"}
        fx = SimpleNamespace(eur_per_unit=dec(1) / dec("1.10"), observed_at=NOW, source="fixture")
        with patch("market_radar_ai.execution.exercise.utcnow", return_value=NOW):
            plan = build_intent(self.broker, fx, "fixture-20261112")
        risk, capital = plan.validate(NOW, self.broker.clock(), Limits())
        self.assertEqual(plan.qty, "1")
        self.assertLess(risk, dec(1))
        self.assertLess(capital, dec(30))
        self.assertEqual(plan.policy_version, "broker-paper-plumbing-v1")

    def test_closed_market_never_submits_entry(self):
        self.broker.open = False
        with self.assertRaises(SafetyError):
            self.start()
        self.assertEqual(self.broker.posts, [])

    def test_wall_clock_advance_during_network_reads_does_not_look_future_dated(self):
        self.broker.now = NOW + timedelta(seconds=1)
        moments = [NOW, NOW, NOW + timedelta(seconds=1), NOW + timedelta(seconds=1),
                   NOW + timedelta(seconds=2), NOW + timedelta(seconds=2)]
        with patch("market_radar_ai.execution.engine.utcnow", side_effect=moments):
            self.engine.submit(intent())
        self.assertEqual(len(self.broker.posts), 1)

    def test_seeded_fill_cancel_timeout_and_restart_sequences(self):
        # Independent fake-broker assertions reject any short/reversing/overlapping exit.
        # Sequences vary when fills and cancellation acknowledgements become visible.
        for seed in range(30):
            rng = random.Random(seed)
            journal = Journal(Path(self.tmp.name) / f"sequence-{seed}.sqlite3")
            broker = Broker()
            engine = Engine(journal, broker)
            try:
                engine.submit(intent(), NOW)
                broker.fill("order-1", rng.choice((1, 2, 4)), 100)
                journal.request_exit("test-source-1", "fault-sequence requested exit")
                for step in range(20):
                    broker.cancel_pending = step < rng.randrange(1, 5)
                    broker.cancel_fault = step == 0 and seed % 3 == 0
                    if step > 5:
                        for order in broker.orders.values():
                            if order["status"] == "pending_cancel":
                                order["status"] = "canceled"
                    if step == 3:
                        journal.close()
                        journal = Journal(Path(self.tmp.name) / f"sequence-{seed}.sqlite3")
                        engine = Engine(journal, broker)
                    engine.tick(NOW)
                    for order in list(broker.orders.values()):
                        if order["side"] == "sell" and order["type"] == "market" and order["status"] not in ORDER_TERMINAL:
                            remaining = dec(order["qty"]) - dec(order["filled_qty"])
                            amount = remaining if step > 12 else min(remaining, dec(1))
                            broker.fill(order["id"], dec(order["filled_qty"]) + amount, 99)
                    if engine.report()["all_intents_terminal"]:
                        break
                engine.tick(NOW)
                self.assertTrue(engine.report()["all_intents_terminal"], f"seed {seed}")
                self.assertEqual(sum(p["side"] == "buy" for p in broker.posts), 1)
                self.assertEqual(broker.positions(), [])
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
