"""Paper-only REST adapter. No configurable host, redirects, retries or live fallback."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .models import SafetyError

PAPER_URL = "https://paper-api.alpaca.markets"


class BrokerError(RuntimeError):
    def __init__(self, status=None):
        self.status = status
        super().__init__(f"paper broker request failed ({status or 'transport'})")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BrokerError(code)


class AlpacaPaper:
    def __init__(self, key, secret, base_url=PAPER_URL):
        if base_url != PAPER_URL:
            raise SafetyError("only the exact Alpaca paper endpoint is allowed")
        if not key or not secret:
            raise SafetyError("paper API credentials missing")
        self._key, self._secret = key, secret
        self._opener = urllib.request.build_opener(NoRedirect())
        self._last_request_at = 0.0

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_API_SECRET"))

    def _request(self, method, path, payload=None, missing_ok=False):
        if not path.startswith("/v2/") or "://" in path or "\\" in path:
            raise SafetyError("invalid broker path")
        return self._http(method, PAPER_URL + path, payload, missing_ok=missing_ok)

    def _http(self, method, url, payload=None, missing_ok=False):
        target = urllib.parse.urlsplit(url)
        allowed = target.hostname == "paper-api.alpaca.markets" or (
            target.hostname == "data.alpaca.markets" and method == "GET")
        if not allowed or target.scheme != "https" or target.port is not None or target.username or target.password:
            raise SafetyError("endpoint outside paper trading/read-only market data allowlist")
        request = urllib.request.Request(url, method=method,
            data=json.dumps(payload, allow_nan=False).encode() if payload is not None else None,
            headers={"APCA-API-KEY-ID": self._key, "APCA-API-SECRET-KEY": self._secret,
                     "Content-Type": "application/json", "User-Agent": "market-radar-demo/1"})
        # Bound aggregate REST traffic in this single worker, including reconciliation.
        # This is a conservative local ceiling, not a claim about account entitlements.
        delay = 0.5 - (time.monotonic() - self._last_request_at)
        if delay > 0:
            time.sleep(delay)
        self._last_request_at = time.monotonic()
        try:
            with self._opener.open(request, timeout=8) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise BrokerError()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise BrokerError(exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # Never log request headers, credentials or raw broker errors/account details.
            raise BrokerError() from None

    def account(self):
        return self._request("GET", "/v2/account")

    def clock(self):
        return self._request("GET", "/v2/clock")

    def positions(self):
        return self._request("GET", "/v2/positions")

    def open_orders(self):
        rows = self._request("GET", "/v2/orders?status=open&nested=true&limit=500")
        if len(rows) >= 500:
            raise SafetyError("open order inventory may be truncated")
        return rows

    def lookup(self, client_id):
        result = self._request("GET", "/v2/orders:by_client_order_id?" +
                               urllib.parse.urlencode({"client_order_id": client_id}), missing_ok=True)
        return self.get_order(result["id"]) if result else None

    def get_order(self, order_id):
        return self._request("GET", "/v2/orders/" + urllib.parse.quote(order_id, safe="") + "?nested=true")

    def submit(self, payload):
        return self._request("POST", "/v2/orders", payload)

    def cancel(self, order_id):
        return self._request("DELETE", "/v2/orders/" + urllib.parse.quote(order_id, safe=""))

    def latest_quote(self, symbol):
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
            raise SafetyError("invalid quote symbol")
        result = self._http("GET", f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest?feed=iex")
        if result.get("symbol") != symbol:
            raise SafetyError("quote symbol mismatch")
        return result["quote"]
