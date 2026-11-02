from __future__ import annotations
import argparse, json
from .providers import CoinGeckoProvider

def main() -> None:
    parser = argparse.ArgumentParser(description="Market Radar AI public data connectivity check")
    parser.add_argument("--crypto-limit", type=int, default=20)
    args = parser.parse_args()
    result = CoinGeckoProvider().discover_eur_markets(limit=args.crypto_limit)
    print(json.dumps({"provider": result.provider, "status": result.status,
        "retrieved_at": result.retrieved_at.isoformat(), "instrument_count": len(result.instruments),
        "sample": [item.model_dump(mode="json") for item in result.instruments[:5]],
        "issues": [issue.model_dump(mode="json") for issue in result.issues]}, indent=2))

if __name__ == "__main__": main()
