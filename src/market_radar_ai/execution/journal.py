"""Single-writer, durable paper intent journal. Persist before any broker mutation."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .models import Intent, SafetyError, canonical, dec, instant, utcnow

TERMINAL = {"CLOSED", "CANCELED"}


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = open(str(self.path) + ".lock", "a+")
        os.chmod(str(self.path) + ".lock", 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock.close()
            raise SafetyError("another worker owns this journal") from exc
        self.db = sqlite3.connect(self.path, isolation_level=None)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, body TEXT NOT NULL,
                state TEXT NOT NULL, risk TEXT NOT NULL, capital TEXT NOT NULL,
                exit_reason TEXT, pnl_eur TEXT, closed_day TEXT);
            CREATE TABLE IF NOT EXISTS operations (
                client_id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES intents(id),
                kind TEXT NOT NULL, payload TEXT NOT NULL, phase TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES intents(id),
                body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations (
                seq INTEGER PRIMARY KEY, order_id TEXT NOT NULL, observed_at TEXT NOT NULL,
                filled_qty TEXT NOT NULL, filled_avg_price TEXT, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, at TEXT NOT NULL, intent_id TEXT,
                kind TEXT NOT NULL, detail TEXT NOT NULL);
        """)
        self.check()

    def close(self):
        self.db.close()
        self.lock.close()

    def check(self):
        if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SafetyError("journal integrity failure")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def event(self, kind, detail, intent_id=None):
        self.db.execute("INSERT INTO events(at,intent_id,kind,detail) VALUES(?,?,?,?)",
                        (utcnow().isoformat(), intent_id, kind, canonical(detail)))

    def get_meta(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key, value):
        self.db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, str(value)))

    def bind_account(self, account_id):
        digest = hashlib.sha256(("alpaca-paper:" + account_id).encode()).hexdigest()
        prior = self.get_meta("account")
        if prior and prior != digest:
            raise SafetyError("journal belongs to a different paper account")
        self.set_meta("account", digest)

    def halt(self, reason, intent_id=None):
        # Latched; transient recovery never silently re-enables entries.
        self.set_meta("entry_halt", reason)
        self.event("ENTRY_HALT", {"reason": reason}, intent_id)

    def get(self, intent_id):
        row = self.db.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone()
        return dict(row) if row else None

    def rows(self, active=False):
        rows = [dict(x) for x in self.db.execute("SELECT * FROM intents ORDER BY rowid")]
        return [x for x in rows if x["state"] not in TERMINAL] if active else rows

    def intent(self, row):
        intent = Intent(**json.loads(row["body"]))
        if intent.fingerprint != row["fingerprint"] or intent.intent_id != row["id"]:
            raise SafetyError("journal intent fingerprint mismatch")
        return intent

    def reserve(self, intent, risk, capital):
        self.db.execute("INSERT INTO intents VALUES(?,?,?,?,?,?,NULL,NULL,NULL)", (
            intent.intent_id, intent.fingerprint, canonical(intent.body()),
            "SUBMISSION_UNKNOWN", str(risk), str(capital)))
        self.event("INTENT_RESERVED", {"fingerprint": intent.fingerprint}, intent.intent_id)

    def prepare(self, intent_id, kind, payload):
        # UNKNOWN is durable before POST. Even a crash before POST is not blindly replayed.
        self.db.execute("INSERT INTO operations VALUES(?,?,?,?,?)", (
            payload["client_order_id"], intent_id, kind, canonical(payload), "UNKNOWN"))
        self.event("SUBMISSION_PREPARED", {"client_order_id": payload["client_order_id"], "kind": kind}, intent_id)

    def operations(self, intent_id):
        return [dict(x) for x in self.db.execute("SELECT * FROM operations WHERE intent_id=? ORDER BY rowid", (intent_id,))]

    def observe(self, intent_id, order, now):
        legs = order.get("legs") or []
        order = {key: value for key, value in order.items() if key != "legs"}
        if not order.get("id") or not order.get("status") or not order.get("symbol"):
            raise SafetyError("malformed broker order")
        filled = dec(order.get("filled_qty", "0"))
        if filled < 0 or filled > dec(order["qty"]):
            raise SafetyError("invalid cumulative fill quantity")
        if filled and (order.get("filled_avg_price") is None or dec(order["filled_avg_price"]) <= 0):
            raise SafetyError("filled order has no execution price")
        previous = self.db.execute("SELECT body FROM orders WHERE id=?", (order["id"],)).fetchone()
        if previous:
            old = json.loads(previous[0])
            if filled < dec(old.get("filled_qty", "0")):
                raise SafetyError("broker cumulative fills moved backwards")
            if old.get("side") != order.get("side") or old.get("symbol") != order.get("symbol"):
                raise SafetyError("broker order identity changed")
        body = canonical(order)
        if not previous or previous[0] != body:
            self.db.execute("INSERT INTO observations(order_id,observed_at,filled_qty,filled_avg_price,body) VALUES(?,?,?,?,?)",
                            (order["id"], now.isoformat(), str(filled), order.get("filled_avg_price"), body))
        self.db.execute("INSERT INTO orders VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                        (order["id"], intent_id, body))
        self.db.execute("UPDATE operations SET phase='OBSERVED' WHERE client_id=? AND intent_id=?",
                        (order.get("client_order_id"), intent_id))
        for leg in legs:
            self.observe(intent_id, leg, now)

    def orders(self, intent_id):
        return [json.loads(x[0]) for x in self.db.execute("SELECT body FROM orders WHERE intent_id=?", (intent_id,))]

    def state(self, intent_id, state):
        self.db.execute("UPDATE intents SET state=? WHERE id=?", (state, intent_id))

    def request_exit(self, intent_id, reason):
        self.db.execute("UPDATE intents SET exit_reason=COALESCE(exit_reason,?) WHERE id=?", (reason, intent_id))

    def complete(self, intent_id, pnl, day, traded):
        self.db.execute("UPDATE intents SET state=?,pnl_eur=?,closed_day=? WHERE id=?",
                        ("CLOSED" if traded else "CANCELED", str(pnl), day, intent_id))
        self.event("RECONCILED_FLAT", {"pnl_eur_after_assumed_costs": str(pnl), "fees_verified": False}, intent_id)

    def daily_losses(self, day):
        return sum((max(-dec(x[0]), dec(0)) for x in self.db.execute(
            "SELECT pnl_eur FROM intents WHERE closed_day=? AND pnl_eur IS NOT NULL", (day,))), dec(0))

    def backup(self, destination):
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
        finally:
            target.close()
        os.chmod(destination, 0o600)
