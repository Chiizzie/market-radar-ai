"""Commission private cost capture only; never log account values or send messages."""
from datetime import UTC, datetime
import json
import os

from market_radar_ai.dashboard.account_sync import Reader, collect, deliver, public_error


def main():
    try:
        reader = Reader(os.environ["TRADING212_API_KEY"], os.environ["TRADING212_API_SECRET"])
        payload = collect(reader, datetime.now(UTC))
        if payload.get("cost_audit", {}).get("schema_version") != "t212-private-cost-audit-v1":
            raise ValueError("cost_audit_missing")
        deliver(payload, os.environ["REVIEW_INGEST_SECRET"], datetime.now(UTC))
        # Account identifiers, holdings, amounts, fills and even counts stay private.
        print(json.dumps({"state": "private_cost_evidence_delivered",
                          "financial_values_logged": False, "model_calls": 0, "orders": 0}))
    except Exception as exc:
        print(json.dumps({"state": "private_cost_evidence_failed", "code": public_error(exc)}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
