"""Bounded, public-data capture for research replay; never authorizes trades."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import ProviderResult
from .quality import validate_candles


def capture_result(result: ProviderResult, *, now: datetime, limit: int = 60) -> dict:
    if now.tzinfo is None or result.retrieved_at.tzinfo is None:
        raise ValueError("Capture timestamps must be timezone-aware")
    if not 1 <= limit <= 120:
        raise ValueError("Capture limit must be between 1 and 120")
    rows = sorted(result.candles, key=lambda row: row.timestamp)[-limit:]
    issues = [issue.model_dump(mode="json") for issue in result.issues]
    issues.extend(issue.model_dump(mode="json") for issue in validate_candles(
        rows, now=now, max_age_seconds=900, expected_interval_seconds=300))
    for row in rows:
        if row.interval != "5m" or (now - row.timestamp).total_seconds() < 300:
            issues.append({"code": "incomplete_or_unexpected_interval", "symbol": row.symbol})
        if row.source != result.provider:
            issues.append({"code": "provider_source_mismatch", "symbol": row.symbol})
    payload = {
        "provider": result.provider,
        "provider_status": result.status,
        "retrieved_at": result.retrieved_at.isoformat(),
        "captured_at_dublin": now.astimezone(ZoneInfo("Europe/Dublin")).isoformat(),
        "candles_returned": len(result.candles),
        "candles_saved": len(rows),
        "candles": [row.model_dump(mode="json") for row in rows],
        "quality_issues": issues,
        "quality_passed_at_capture": result.status == "ok" and not issues,
        "account_broker_eligibility": "unknown",
        "news_evidence": "not_collected",
        "currency_conversion": "not_applied_native_quotes_preserved",
        "disposition": "NO_ACTION",
        "research_only": True,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"payload": payload, "payload_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from .providers.kraken import KrakenProvider
    from .providers.yahoo import YahooFinanceProvider
    results = [YahooFinanceProvider().fetch_history("MSFT", period="1d", interval="5m"),
               KrakenProvider().fetch_ohlc("XBTEUR", interval_minutes=5)]
    now = datetime.now(timezone.utc)
    document = {"format_version": 1, "purpose": "historical_research_replay_not_live_signal",
                "captures": [capture_result(result, now=now) for result in results]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    for capture in document["captures"]:
        p = capture["payload"]
        print(json.dumps({key: p[key] for key in ("provider", "provider_status", "candles_saved",
                         "quality_passed_at_capture", "quality_issues", "disposition")}))


if __name__ == "__main__":
    main()
