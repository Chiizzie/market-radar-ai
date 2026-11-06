"""Bounded, public-data capture for research replay; never authorizes trades."""
from __future__ import annotations

import argparse
import hashlib
import json
from time import monotonic
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import ProviderResult
from .quality import validate_candles
from .limits import STOCK_RESEARCH_LIMIT, CRYPTO_RESEARCH_LIMIT


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


def capture_markets(stock_symbols, crypto_pairs, *, stock_fetch, crypto_fetch,
                    now=None, clock=monotonic, per_market_limit=10, cache=None,
                    stock_provider='yahoo_finance') -> dict:
    """Stocks first; separate quotas prevent either market starving the other."""
    if not 1 <= per_market_limit <= STOCK_RESEARCH_LIMIT:
        raise ValueError("Per-market research capacity exceeded")
    captures, coverage = [], {}
    for market, symbols, fetch in (("stocks", stock_symbols, stock_fetch),
                                   ("crypto", crypto_pairs, crypto_fetch)):
        unique = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        limit=min(per_market_limit, STOCK_RESEARCH_LIMIT if market=='stocks' else CRYPTO_RESEARCH_LIMIT)
        selected = unique[:limit]
        successful = 0
        fresh = 0
        not_requested = 0
        for symbol in selected:
            start = clock()
            try:
                provider_name = stock_provider if market == 'stocks' else 'kraken'
                check_time = now or datetime.now(timezone.utc)
                result = cache.get(provider_name, symbol, now=check_time) if cache else None
                cache_hit = result is not None
                if result is None:
                    result = fetch(symbol)
                if not isinstance(result, ProviderResult):
                    raise ValueError("invalid_provider_result")
            except Exception:
                cache_hit = False
                from .models import ValidationIssue
                result = ProviderResult(provider=market, retrieved_at=datetime.now(timezone.utc),
                    status="error", issues=[ValidationIssue(code="fetch_failed",
                    message="Provider request failed", symbol=symbol)])
            if any(row.symbol.upper() != symbol for row in result.candles):
                from .models import ValidationIssue
                result = result.model_copy(update={"issues": [*result.issues,
                    ValidationIssue(code="requested_symbol_mismatch", message="Unexpected symbol in provider response", symbol=symbol)]})
            if cache is not None and not cache_hit:
                cache.put(provider_name, symbol, result, now=now or datetime.now(timezone.utc))
            not_requested += int(
                market == 'stocks' and result.provider == 'alpaca_iex'
                and result.status == 'ok' and not result.candles
                and {i.code for i in result.issues} in ({'regular_session_not_started'}, {'regular_session_warmup'}))
            elapsed = max(0, clock() - start)
            captured = capture_result(result, now=now or datetime.now(timezone.utc))
            captured.update(market=market, requested_symbol=symbol, cache_hit=cache_hit,
                            request_elapsed_seconds=round(elapsed, 3))
            captures.append(captured)
            successful += int(result.status == "ok" and bool(result.candles))
            fresh += int(captured["payload"]["quality_passed_at_capture"])
        coverage[market] = dict(requested=len(unique), attempted=len(selected),
            successful=successful, quality_passed=fresh, not_requested=not_requested,
            deferred=unique[limit:])
    return {"format_version": 2, "purpose": "historical_research_replay_not_live_signal",
            "coverage_scope": "explicit_requested_symbols_not_full_market",
            "coverage": coverage, "captures": captures}


def connectivity_exit_code(document):
    # A valid empty series is a data gap, not a failed HTTP/provider connection.
    rows=document['captures']
    for market in {c.get('market','unknown') for c in rows}:
        group=[c['payload'] for c in rows if c.get('market','unknown')==market]
        expected_wait = {'regular_session_not_started', 'regular_session_warmup'}
        # Isolated provider/symbol gaps remain visible and blocked; a whole
        # market outage still fails the workflow. Broader discovery must not
        # discard 69 healthy captures because one illiquid pair is unavailable.
        healthy=any(p['provider_status']=='ok' and p.get('candles') for p in group)
        waiting=all(p['provider_status']=='ok' and any(i['code'] in expected_wait for i in p.get('quality_issues',[])) for p in group)
        if group and not healthy and not waiting:return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stocks", nargs="+", default=["MSFT", "AAPL", "NVDA"])
    parser.add_argument("--crypto", nargs="+", default=["XBTEUR", "ETHEUR"])
    parser.add_argument('--stock-provider', choices=['yahoo_finance', 'alpaca_iex'], default='yahoo_finance')
    parser.add_argument('--per-market-limit', type=int, default=10)
    parser.add_argument('--universe', type=Path, help='JSON object with stocks and crypto symbol lists')
    parser.add_argument('--queue-db', type=Path, help='Persistent fair scan queue; required with --universe')
    args = parser.parse_args()
    if not 1<=args.per_market_limit<=STOCK_RESEARCH_LIMIT:
        parser.error('Per-market research capacity exceeded')
    if bool(args.universe) != bool(args.queue_db):
        parser.error('--universe and --queue-db must be supplied together')
    selection = None
    if args.universe:
        from .queue import ScanQueue
        universe = json.loads(args.universe.read_text())
        if not isinstance(universe, dict) or set(universe) != {'stocks', 'crypto'} or any(
            not isinstance(v, list) or any(not isinstance(s, str) for s in v) for v in universe.values()):
            parser.error('Universe must contain stocks and crypto string lists')
        args.queue_db.parent.mkdir(parents=True, exist_ok=True)
        queue = ScanQueue(args.queue_db)
        for market, symbols in universe.items():
            queue.replace_universe(market, symbols)
        selection = queue.select(now=datetime.now(timezone.utc), stocks=10, crypto=5)
        args.stocks = selection['stocks']['selected']
        args.crypto = selection['crypto']['selected']
    from .providers.kraken import KrakenProvider
    from .providers.yahoo import YahooFinanceProvider
    if args.stock_provider == 'alpaca_iex':
        from .providers.alpaca import AlpacaIexProvider
        import os
        if os.environ.get('ENABLE_BROAD_DISCOVERY') == 'true':
            from .providers.alpaca_batch import fetch_histories
            results=fetch_histories(list(dict.fromkeys(args.stocks))[:args.per_market_limit],env=os.environ)
            stock_fetch=results.__getitem__
        else:
            stock_fetch = AlpacaIexProvider().fetch_history
    else:
        stock_fetch = lambda symbol: YahooFinanceProvider().fetch_history(symbol, period="1d", interval="5m")
    from concurrent.futures import ThreadPoolExecutor
    pairs=list(dict.fromkeys(args.crypto))[:min(args.per_market_limit,CRYPTO_RESEARCH_LIMIT)]
    def fetch_pair(pair):
        return KrakenProvider().fetch_ohlc(pair,interval_minutes=5)
    with ThreadPoolExecutor(max_workers=2) as executor:
        crypto_results=dict(zip(pairs,executor.map(fetch_pair,pairs)))
    document = capture_markets(args.stocks, args.crypto,
        stock_fetch=stock_fetch, stock_provider=args.stock_provider, per_market_limit=args.per_market_limit,
        crypto_fetch=crypto_results.__getitem__)
    if selection is not None:
        document['queue_selection'] = selection
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document["coverage"], indent=2))
    for capture in document["captures"]:
        p = capture["payload"]
        print(json.dumps({"symbol": capture["requested_symbol"],
            "elapsed_seconds": capture["request_elapsed_seconds"],
            "provider_status": p["provider_status"], "candles_saved": p["candles_saved"],
            "quality_passed": p["quality_passed_at_capture"], "issues": p["quality_issues"]}))
    # Report provider failures as a failing connectivity check, preserving the evidence first.
    return connectivity_exit_code(document)


if __name__ == "__main__":
    raise SystemExit(main())
