"""Strict, decimal-based inputs. A reviewed idea is not an execution instruction."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from zoneinfo import ZoneInfo


class SafetyError(RuntimeError):
    pass


def dec(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SafetyError("invalid decimal") from exc
    if not result.is_finite():
        raise SafetyError("non-finite decimal")
    return result


def instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise SafetyError("invalid timestamp") from exc
    if result.tzinfo is None:
        raise SafetyError("timestamp requires timezone")
    return result.astimezone(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def utcnow():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Limits:
    # Demo engineering defaults, independent of scanner budgets and strategy rules.
    per_trade_eur: Decimal = Decimal("20")
    combined_risk_eur: Decimal = Decimal("40")
    daily_loss_and_risk_eur: Decimal = Decimal("40")
    per_trade_capital_eur: Decimal = Decimal("500")
    total_capital_eur: Decimal = Decimal("1000")
    max_positions: int = 3
    quote_age_seconds: int = 5
    fx_age_seconds: int = 900
    spread_bps: Decimal = Decimal("20")
    roundtrip_cost_bps: Decimal = Decimal("40")
    close_buffer_seconds: int = 300
    entry_buffer_seconds: int = 600


@dataclass(frozen=True)
class Intent:
    intent_id: str
    source_event_id: str
    policy_version: str
    symbol: str
    qty: str
    limit_usd: str
    stop_usd: str
    target_usd: str
    bid_usd: str
    ask_usd: str
    usd_per_eur: str
    created_at: str
    quote_at: str
    fx_at: str
    expires_at: str
    session_close: str
    mode: str = "paper"

    def body(self):
        return asdict(self)

    @property
    def fingerprint(self):
        return hashlib.sha256(canonical(self.body()).encode()).hexdigest()

    def client_id(self, role):
        digest = hashlib.sha256(self.intent_id.encode()).hexdigest()[:32]
        return f"mrdemo-{digest}-{role}"

    def validate(self, now, clock, limits):
        if self.mode != "paper":
            raise SafetyError("only paper intents are supported")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", self.intent_id):
            raise SafetyError("invalid intent identity")
        if not self.source_event_id.strip() or not self.policy_version.strip():
            raise SafetyError("source event and policy version are required")
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", self.symbol):
            raise SafetyError("invalid US equity symbol")
        qty, entry, stop, target, bid, ask, fx = map(dec, (
            self.qty, self.limit_usd, self.stop_usd, self.target_usd,
            self.bid_usd, self.ask_usd, self.usd_per_eur))
        if qty <= 0 or qty != qty.to_integral_value():
            raise SafetyError("whole positive shares only")
        if not Decimal("1") <= stop < entry < target or not stop < bid <= ask <= entry:
            raise SafetyError("invalid long plan or nonmarketable entry")
        if any(p != p.quantize(Decimal("0.01")) for p in (entry, stop, target)):
            raise SafetyError("prices must use whole cents")
        if fx <= 0 or (ask - bid) / ((ask + bid) / 2) * 10000 > limits.spread_bps:
            raise SafetyError("invalid FX or excessive spread")
        for field, max_age in ((self.created_at, 300), (self.quote_at, limits.quote_age_seconds),
                               (self.fx_at, limits.fx_age_seconds), (clock["timestamp"], 10)):
            age = (now - instant(field)).total_seconds()
            if not 0 <= age <= max_age:
                raise SafetyError("stale or future evidence")
        close = instant(clock["next_close"])
        if not clock.get("is_open") or instant(self.session_close) != close:
            raise SafetyError("market closed or session mismatch")
        if not now < instant(self.expires_at) <= close - timedelta(seconds=limits.entry_buffer_seconds):
            raise SafetyError("expired intent or too close to market close")
        if now >= close - timedelta(seconds=limits.entry_buffer_seconds):
            raise SafetyError("entry cutoff")
        if now.astimezone(ZoneInfo("Europe/Dublin")).hour >= 22:
            raise SafetyError("Dublin entry cutoff")
        risk, capital = self.reserves(limits)
        if risk > limits.per_trade_eur or capital > limits.per_trade_capital_eur:
            raise SafetyError("per-trade risk or capital limit")
        return risk, capital

    def reserves(self, limits):
        qty, entry, stop, fx = map(dec, (self.qty, self.limit_usd, self.stop_usd, self.usd_per_eur))
        costs = qty * entry * limits.roundtrip_cost_bps / 10000
        return (qty * (entry - stop) + costs) / fx, qty * entry / fx

    def entry_order(self):
        return {"symbol": self.symbol, "qty": self.qty, "side": "buy", "type": "limit",
                "time_in_force": "day", "limit_price": self.limit_usd,
                "order_class": "bracket", "extended_hours": False,
                "client_order_id": self.client_id("entry"),
                "take_profit": {"limit_price": self.target_usd},
                "stop_loss": {"stop_price": self.stop_usd}}
