"""Bounded, read-only Alpaca IEX connectivity capture; never a trade signal."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from .models import Candle

PATHS = {"quote": "/v2/stocks/NVDA/quotes/latest", "bars": "/v2/stocks/NVDA/bars", "news": "/v1beta1/news"}


class DataError(Exception):
    pass


class AlpacaReader:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def get(self, kind, params):
        # Fixed origin and allowlisted paths; no account or order endpoints.
        path = PATHS[kind]
        key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
        if not key or not secret:
            raise DataError("credentials_missing")
        try:
            response = self.session.get("https://data.alpaca.markets" + path,
                params=params, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                timeout=15, allow_redirects=False)
            if response.status_code != 200:
                raise DataError(f"http_{response.status_code}")
            result = response.json()
            if not isinstance(result, dict):
                raise DataError("invalid_response")
            return result
        except DataError:
            raise
        except Exception:
            raise DataError("transport_or_json_error") from None


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone_required")
    return result.astimezone(timezone.utc)


def number(value, positive=True):
    result = Decimal(str(value))
    if not result.is_finite() or (result <= 0 if positive else result < 0):
        raise ValueError("invalid_number")
    return result


def capture(reader=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    reader = reader or AlpacaReader()
    start = now.astimezone(ZoneInfo("America/New_York")).replace(hour=9, minute=30, second=0, microsecond=0)
    result = {"version": "alpaca-data-check-v1", "observed_at": now.isoformat(),
        "observed_at_dublin": now.astimezone(ZoneInfo("Europe/Dublin")).isoformat(),
        "symbol": "NVDA", "feed": "iex", "currency": "USD", "trade_authorized": False,
        "model_calls": 0, "coverage": "IEX only; not consolidated NBBO or Trading 212 executable prices",
        "quote": {}, "bars": {}, "news": {}}
    for kind in PATHS:
        try:
            params = {"feed": "iex"}
            if kind == "bars":
                if now <= start:
                    raise DataError("regular_session_not_started")
                params.update(timeframe="5Min", start=start.isoformat(), end=now.isoformat(), limit=1000, adjustment="raw")
            if kind == "news":
                params = {"symbols": "NVDA", "start": (now-timedelta(days=3)).isoformat(), "end": now.isoformat(),
                    "limit": 20, "include_content": "false", "sort": "desc"}
            data = reader.get(kind, params)
            if kind == "quote":
                quote = data["quote"]
                age = (now-timestamp(quote["t"])).total_seconds()
                bid, ask = number(quote["bp"]), number(quote["ap"])
                if ask < bid or age < 0:
                    raise ValueError("invalid_quote")
                result[kind] = {"status": "fresh" if age <= 120 else "stale", "age_seconds": age,
                    "timestamp": quote["t"], "bid_usd": str(bid), "ask_usd": str(ask),
                    "spread_usd": str(ask-bid)}
            elif kind == "bars":
                if data.get("next_page_token"):
                    raise DataError("pagination_incomplete")
                rows = []
                unfinished = 0
                if "bars" not in data or (data["bars"] is not None and not isinstance(data["bars"], list)):
                    raise ValueError("missing_bars")
                for bar in data["bars"] or []:
                    t = timestamp(bar["t"])
                    if t < start or t > now:
                        raise ValueError("out_of_window_bar")
                    if t+timedelta(minutes=5) > now:
                        unfinished += 1
                        continue
                    candle = Candle(symbol="NVDA", interval="5m", timestamp=t,
                        open=number(bar["o"]), high=number(bar["h"]), low=number(bar["l"]),
                        close=number(bar["c"]), volume=number(bar["v"], False), quote_currency="USD", source="alpaca_iex")
                    if rows and t <= timestamp(rows[-1]["timestamp"]):
                        raise ValueError("unordered_bars")
                    rows.append(candle.model_dump(mode="json"))
                age = (now-timestamp(rows[-1]["timestamp"])-timedelta(minutes=5)).total_seconds() if rows else None
                gaps = sum(timestamp(b["timestamp"])-timestamp(a["timestamp"]) != timedelta(minutes=5) for a,b in zip(rows, rows[1:]))
                result[kind] = {"status": "fresh" if rows and age <= 600 else "stale_or_empty",
                    "count": len(rows), "completed_bar_age_seconds": age, "gap_count": gaps,
                    "unfinished_bars_excluded": unfinished, "candles": rows,
                    "minimum_20_bars_met": len(rows) >= 20}
            else:
                items = []
                if not isinstance(data.get("news"), list):
                    raise ValueError("missing_news")
                for item in data["news"]:
                    created = timestamp(item["created_at"])
                    if created > now or "NVDA" not in item["symbols"]:
                        raise ValueError("invalid_news_metadata")
                    items.append({key: item.get(key) for key in ("id", "headline", "url", "source", "created_at", "updated_at", "symbols")})
                result[kind] = {"status": "accessible", "count": len(items), "items": items,
                    "more_available": bool(data.get("next_page_token")), "catalysts_verified": False}
        except DataError as exc:
            result[kind] = {"status": "error", "reason": str(exc)}
        except Exception:
            result[kind] = {"status": "error", "reason": "invalid_provider_payload"}
    result["state"] = "data_received" if all(result[k]["status"] != "error" for k in PATHS) else "partial_or_blocked"
    return result


def main():
    result = capture()
    target = Path("artifacts/alpaca-check/result.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"state": result["state"], **{k: {x:v for x,v in result[k].items() if x not in ("candles", "items")} for k in PATHS}}))


if __name__ == "__main__":
    main()
