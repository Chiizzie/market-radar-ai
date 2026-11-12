"""Conservative, long-only demo order manager with reconciliation before mutations.

Cancellation acknowledgement is not cancellation completion. Unknown POST outcomes
are never resubmitted, even after a 404. Partial bracket entries are canceled and
flattened after terminal order/position reconciliation; they are NOT called protected.
"""
import json
from datetime import timedelta
from zoneinfo import ZoneInfo

from .alpaca import BrokerError
from .journal import TERMINAL
from .models import Limits, SafetyError, dec, instant, utcnow

ORDER_TERMINAL = {"filled", "canceled", "expired", "rejected"}
PROTECTIVE = {"new", "accepted_for_bidding"}
ORDER_STATUSES = ORDER_TERMINAL | PROTECTIVE | {
    "accepted", "pending_new", "partially_filled", "done_for_day", "pending_cancel",
    "pending_replace", "replaced", "stopped", "suspended", "calculated", "held"}


def flatten_orders(orders):
    result = []
    for order in orders:
        result.append(order)
        result.extend(flatten_orders(order.get("legs") or []))
    return result


class Engine:
    def __init__(self, journal, broker, limits=None):
        self.journal, self.broker = journal, broker
        self.limits = limits or Limits()
        self.last_reconciled_at = None
        self.last_error = None

    def account(self):
        account = self.broker.account()
        if not account.get("id") or account.get("currency") != "USD":
            raise SafetyError("paper account must have an identity and USD currency")
        self.journal.bind_account(account["id"])
        return account

    def submit(self, intent, now=None):
        supplied_now = now is not None
        now = now or utcnow()
        previous = self.journal.get(intent.intent_id)
        if previous:
            if previous["fingerprint"] != intent.fingerprint:
                raise SafetyError("same intent ID has different immutable contents")
            # A duplicate signal/restart is a read/reconcile operation, never another POST.
            self.tick(now)
            return self.journal.get(intent.intent_id)
        self.tick(now)
        if self.last_error or self.journal.get_meta("entry_halt"):
            raise SafetyError("entries halted; inspect reconciliation report")
        account = self.account()
        if account.get("status") != "ACTIVE" or any(account.get(k) is not False for k in
                ("trading_blocked", "account_blocked", "trade_suspended_by_user")):
            raise SafetyError("account not explicitly available for paper trading")
        clock = self.broker.clock()
        if not supplied_now:
            now = utcnow()
        risk, capital = intent.validate(now, clock, self.limits)
        active = self.journal.rows(active=True)
        if any(self.journal.intent(row).symbol == intent.symbol for row in active):
            raise SafetyError("one active intent per symbol")
        used_risk = sum((dec(row["risk"]) for row in active), dec(0))
        used_capital = sum((dec(row["capital"]) for row in active), dec(0))
        day = now.astimezone(ZoneInfo("Europe/Dublin")).date().isoformat()
        if len(active) >= self.limits.max_positions:
            raise SafetyError("position count limit")
        if risk + used_risk > self.limits.combined_risk_eur:
            raise SafetyError("combined risk limit")
        if risk + used_risk + self.journal.daily_losses(day) > self.limits.daily_loss_and_risk_eur:
            raise SafetyError("daily loss plus reserved risk limit")
        if capital + used_capital > self.limits.total_capital_eur:
            raise SafetyError("capital reservation limit")
        # Do not use margin buying power. Pending entries also reserve cash.
        reserved_usd = sum((dec(self.journal.intent(row).qty) *
                            dec(self.journal.intent(row).limit_usd) for row in active), dec(0))
        if dec(account["cash"]) < dec(intent.qty) * dec(intent.limit_usd) + reserved_usd:
            raise SafetyError("insufficient unreserved cash")
        payload = intent.entry_order()
        with self.journal.transaction():
            self.journal.check()
            self.journal.reserve(intent, risk, capital)
            self.journal.prepare(intent.intent_id, "entry", payload)
        self._post(intent.intent_id, payload, now)
        return self.journal.get(intent.intent_id)

    def _post(self, intent_id, payload, now):
        try:
            order = self.broker.submit(payload)
        except BrokerError:
            self.journal.halt("submission outcome unknown; reconcile client ID", intent_id)
            return
        self._validate_identity(order, payload)
        with self.journal.transaction():
            self.journal.observe(intent_id, order, now)
        # Acknowledgement alone never marks a position entered or protected.

    @staticmethod
    def _validate_identity(order, payload):
        for field in ("symbol", "side", "client_order_id", "type"):
            if order.get(field) != payload.get(field):
                raise SafetyError("broker response does not match submitted order")
        if dec(order["qty"]) != dec(payload["qty"]):
            raise SafetyError("broker changed requested quantity")
        if payload.get("order_class") == "bracket" and order.get("order_class") != "bracket":
            raise SafetyError("broker did not acknowledge bracket order")

    def tick(self, now=None):
        supplied_now = now is not None
        now = now or utcnow()
        self.last_error = None
        try:
            self.journal.check()
            self.account()
            clock = self.broker.clock()
            if not supplied_now:
                now = utcnow()
            if not 0 <= (now - instant(clock["timestamp"])).total_seconds() <= 10:
                raise SafetyError("stale broker clock")
            for row in self.journal.rows(active=True):
                self._refresh(row, now)
            positions = self._inventory()
            for row in self.journal.rows(active=True):
                self._manage(row, positions, clock, now)
            self.last_reconciled_at = now.isoformat()
        except (BrokerError, SafetyError, KeyError, TypeError, ValueError) as exc:
            self.last_error = type(exc).__name__ + ": " + str(exc)
            self.journal.halt(self.last_error)
        return self.report()

    def _refresh(self, row, now):
        for operation in self.journal.operations(row["id"]):
            order = self.broker.lookup(operation["client_id"])
            if order is None:
                self.journal.db.execute("UPDATE operations SET phase='UNKNOWN' WHERE client_id=?", (operation["client_id"],))
                self.journal.state(row["id"], "RECONCILIATION_REQUIRED")
                self.journal.halt("order lookup missing; no automatic resubmission", row["id"])
                continue
            self._validate_identity(order, json.loads(operation["payload"]))
            with self.journal.transaction():
                self.journal.observe(row["id"], order, now)
        # A nested response can omit a previously observed leg: query it individually.
        for order in self.journal.orders(row["id"]):
            if order["status"] not in ORDER_TERMINAL:
                refreshed = self.broker.get_order(order["id"])
                if refreshed["id"] != order["id"]:
                    raise SafetyError("broker changed order identity")
                with self.journal.transaction():
                    self.journal.observe(row["id"], refreshed, now)

    def _inventory(self):
        positions = {}
        for position in self.broker.positions():
            symbol = position["symbol"]
            if symbol in positions:
                raise SafetyError("duplicate broker position record")
            positions[symbol] = dec(position["qty"])
        known = {order["id"] for row in self.journal.rows() for order in self.journal.orders(row["id"])}
        foreign = [order for order in flatten_orders(self.broker.open_orders()) if order["id"] not in known]
        if foreign:
            self.journal.halt("unowned open order; dedicated paper account required")
        symbols = {self.journal.intent(row).symbol for row in self.journal.rows(active=True)}
        if any(qty != 0 and symbol not in symbols for symbol, qty in positions.items()):
            self.journal.halt("unowned broker position; no automatic liquidation")
        # Unrelated foreign exposure stops entries but does not stop management of ours.
        if any(order["symbol"] in symbols for order in foreign):
            raise SafetyError("unowned order in managed symbol; exposure ambiguous")
        return positions

    @staticmethod
    def _quantity(orders):
        return sum((dec(order["filled_qty"]) * (1 if order["side"] == "buy" else -1)
                    for order in orders), dec(0))

    def _protection(self, intent, orders, remaining):
        stops = [o for o in orders if o["side"] == "sell" and o.get("type") == "stop"
                 and o["status"] in PROTECTIVE
                 and dec(o.get("stop_price", 0)) == dec(intent.stop_usd)
                 and dec(o["qty"]) - dec(o["filled_qty"]) == remaining]
        return remaining > 0 and len(stops) == 1

    def _manage(self, row, positions, clock, now):
        intent = self.journal.intent(row)
        operations = self.journal.operations(row["id"])
        if any(op["phase"] == "UNKNOWN" for op in operations):
            self.journal.state(row["id"], "RECONCILIATION_REQUIRED")
            return
        orders = self.journal.orders(row["id"])
        if any(o["status"] not in ORDER_STATUSES or o["status"] in {"replaced", "pending_replace"}
               or o["symbol"] != intent.symbol or o["side"] not in {"buy", "sell"} for o in orders):
            raise SafetyError("unsupported broker transition requires reconciliation")
        entry = next((o for o in orders if o.get("client_order_id") == intent.client_id("entry")), None)
        if entry is None:
            raise SafetyError("entry order missing")
        remaining = self._quantity(orders)
        observed = positions.get(intent.symbol, dec(0))
        if remaining < 0 or observed != remaining:
            self.journal.state(row["id"], "RECONCILIATION_REQUIRED")
            self.journal.halt("position/fill mismatch; never guess an exit quantity", row["id"])
            return
        if remaining == 0 and all(o["status"] in ORDER_TERMINAL for o in orders):
            proceeds = sum((dec(o["filled_qty"]) * dec(o.get("filled_avg_price") or 0) *
                            (1 if o["side"] == "sell" else -1) for o in orders), dec(0))
            costs = dec(entry["filled_qty"]) * dec(intent.limit_usd) * self.limits.roundtrip_cost_bps / 10000
            pnl = (proceeds - costs) / dec(intent.usd_per_eur)
            self.journal.complete(row["id"], pnl, now.astimezone(ZoneInfo("Europe/Dublin")).date().isoformat(),
                                  dec(entry["filled_qty"]) > 0)
            return
        exit_reason = row["exit_reason"]
        if 0 < dec(entry["filled_qty"]) < dec(entry["qty"]) and not exit_reason:
            exit_reason = "partial entry has no active bracket protection"
            self.journal.halt(exit_reason, row["id"])
        if remaining > 0 and not self._protection(intent, orders, remaining) and not exit_reason:
            exit_reason = "protective stop missing, rejected or wrong quantity"
            self.journal.halt(exit_reason, row["id"])
        # Use the original session deadline across restarts; next_close may roll to tomorrow.
        if now >= instant(intent.session_close) - timedelta(seconds=self.limits.close_buffer_seconds):
            exit_reason = exit_reason or "session deadline"
        if not dec(entry["filled_qty"]) and (now >= instant(intent.expires_at)
                                             or self.journal.get_meta("entry_halt")):
            exit_reason = exit_reason or "entry expired or kill switch"
        if remaining == 0 and dec(entry["filled_qty"]) > 0:
            exit_reason = exit_reason or "flat; cancel surviving sibling"
        if exit_reason:
            self.journal.request_exit(row["id"], exit_reason)
            self._exit(intent, orders, operations, remaining, clock, now)
        else:
            self.journal.state(row["id"], "OPEN_PROTECTED" if remaining else "ENTRY_WORKING")

    def _exit(self, intent, orders, operations, remaining, clock, now):
        exits = [op for op in operations if op["kind"] == "exit"]
        exit_cids = {op["client_id"] for op in exits}
        # Never cancel a working flatten order. Wait for its fills/terminal state.
        if any(o.get("client_order_id") in exit_cids and o["status"] not in ORDER_TERMINAL for o in orders):
            self.journal.state(intent.intent_id, "EXIT_WORKING")
            return
        if remaining > 0 and (not clock["is_open"] or now >= instant(intent.session_close)):
            self.journal.state(intent.intent_id, "UNRESOLVED_SESSION_CLOSED")
            self.journal.halt("session closed with remaining exposure; retain existing protection", intent.intent_id)
            return
        pending = [o for o in orders if o["status"] not in ORDER_TERMINAL]
        if pending:
            self.journal.state(intent.intent_id, "EXIT_CANCEL_PENDING")
            for order in pending:
                if order["status"] != "pending_cancel":
                    self.journal.event("CANCEL_REQUEST", {"order_id": order["id"]}, intent.intent_id)
                    try:
                        self.broker.cancel(order["id"])
                    except BrokerError:
                        self.journal.halt("cancel outcome uncertain; await terminal broker state", intent.intent_id)
            return
        if remaining == 0:
            return  # Next reconciliation records flat only after all orders are terminal.
        if not clock["is_open"] or now >= instant(intent.session_close):
            self.journal.state(intent.intent_id, "UNRESOLVED_SESSION_CLOSED")
            self.journal.halt("session closed with remaining exposure", intent.intent_id)
            return
        if len(exits) >= 3:
            self.journal.state(intent.intent_id, "UNRESOLVED_EXIT_RETRIES")
            self.journal.halt("bounded exit attempts exhausted", intent.intent_id)
            return
        payload = {"symbol": intent.symbol, "qty": str(remaining), "side": "sell", "type": "market",
                   "time_in_force": "day", "extended_hours": False,
                   "client_order_id": intent.client_id(f"exit{len(exits)}")}
        with self.journal.transaction():
            self.journal.check()
            self.journal.prepare(intent.intent_id, "exit", payload)
            self.journal.state(intent.intent_id, "EXIT_SUBMISSION_UNKNOWN")
        self._post(intent.intent_id, payload, now)

    def report(self):
        items = []
        for row in self.journal.rows():
            intent, orders = self.journal.intent(row), self.journal.orders(row["id"])
            remaining = self._quantity(orders)
            items.append({"intent_id": row["id"], "symbol": intent.symbol, "state": row["state"],
                          "entry_limit_usd": intent.limit_usd, "stop_usd": intent.stop_usd,
                          "target_usd": intent.target_usd, "remaining_from_fills": str(remaining),
                          "protection_observed": self._protection(intent, orders, remaining),
                          "exit_reason": row["exit_reason"], "reserved_risk_eur": row["risk"],
                          "pnl_eur_after_assumed_costs": row["pnl_eur"],
                          "orders": [{k: o.get(k) for k in ("id", "client_order_id", "side", "type", "status",
                                                              "qty", "filled_qty", "filled_avg_price")} for o in orders]})
        return {"schema": "broker-paper-engine-v1", "mode": "paper", "live_orders_enabled": False,
                "scanner_auto_execution_enabled": False, "fees_verified": False,
                "entry_halt": self.journal.get_meta("entry_halt"), "last_error": self.last_error,
                "last_reconciled_at": self.last_reconciled_at,
                "all_intents_terminal": all(row["state"] in TERMINAL for row in self.journal.rows()),
                "intents": items}
