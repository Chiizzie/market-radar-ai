# Phase 1 — Market data layer

## Current adapters

| Adapter | Purpose | Currency / interval | Important limitation |
|---|---|---|---|
| CoinGecko | Discover crypto markets ranked by market cap | EUR market metrics | Discovery feed only; ticker symbols are not unique identifiers. Preserve CoinGecko IDs when mapping to exchange pairs. |
| Kraken | Exchange OHLC candles | Requested interval; EUR quote inferred only for EUR-suffixed pairs | Kraken pair aliases must be resolved against its AssetPairs catalogue before automated batch requests. API returns a bounded recent candle history. |
| Yahoo Finance (`yfinance`) | Equity and fallback historical candles | Provider quote currency; intraday history is provider-limited | Not an execution feed; availability and timestamps can vary. |

## Data-quality rules

- Timestamps must be timezone-aware and are normalized to UTC.
- OHLC values must be positive and internally consistent; volume cannot be negative.
- Quality checks report stale candles, duplicate symbol/timestamp rows, future timestamps and interval gaps.
- Data is not silently repaired. A downstream decision gate must reject or explicitly handle quality issues.
- EUR conversion is not yet performed for USD-quoted equities. Currency conversion must use a timestamped FX source and retain both native and converted values before any EUR risk calculation.

## Baseline ranker

The initial ranker is deliberately transparent: recent price momentum plus relative recent volume. It is a candidate-ordering heuristic only, not a trade signal. It must not produce entries, stops, targets or position sizes. More robust features (VWAP, volatility, liquidity, session-aware volume, breakout/retest structure) follow after universe and candle coverage are validated.

## Next implementation gates

1. Add full eligible-equity universe discovery with exchange, instrument type, active status and duplicate handling.
2. Resolve crypto assets to supported Kraken EUR pairs and record unsupported assets rather than silently substituting pairs.
3. Add a timestamped EUR FX adapter for non-EUR stock quotes.
4. Build a batch orchestrator with per-provider rate limits, retries, caching and a scan report.
5. Run repeatable coverage and data-quality tests before any LLM agent consumes the feed.

Kraken's final OHLC row is the currently forming interval and is excluded by the adapter. This is intentional: first-pass technical analysis must use completed candles only.
