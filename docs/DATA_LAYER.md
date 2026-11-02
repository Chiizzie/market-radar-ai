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

## Verification and conservative adapter behavior

Run `python -m pytest -q` for offline tests and
`python -m market_radar_ai.market_data.cli --provider all` for explicit live smoke checks.
The live command exits nonzero on provider errors or empty results; successful transport
does not prove freshness, broker eligibility, or full universe coverage.
Yahoo supports intraday intervals only, excludes forming bars, and rejects unknown
quote currencies and timezone-naive timestamps. Freshness is checked on the latest
bar per symbol/interval/source; older lookback bars remain valid history. Gap checks
are not exchange-calendar-aware yet.

No provider listing establishes Trading 212 Invest or Robinhood Europe eligibility.
Broker verification, FX conversion, position lifecycle/forced paper exits, and AI
cost limits remain implementation gates. The current risk helper is a pre-entry
check, not an overnight-position manager. No paid AI or live order API is connected.

## Evidence-based admission and batch screening

`market_data.screening.screen_batch` is the new conservative batch entry point.
It checks evidence before baseline ranking and accounts for every rejected input.
It is an offline boundary over supplied provider results, not a network scheduler.

- Equities require Trading 212 Invest evidence; crypto requires Robinhood Europe
  evidence. Records include provider identity, venue, broker instrument ID,
  source, verification time and expiry. Unknown/expired eligibility fails closed.
- Non-EUR closes require a positive finite timestamped EUR-per-native-unit FX
  quote no older than 15 minutes. Native prices and FX provenance are preserved.
- Partial/error results, short histories, stale or forming bars, currency/identity
  mismatches and duplicate-symbol collisions are rejected before ranking.
- Default admission requires 20 completed 5-minute candles, newest no older than
  10 minutes. Closed sessions fail freshness; session calendars remain pending.
- The shortlist is research only. It does not authorize orders, invoke AI, or
  bypass the separate risk/time gate. Trade-level FX costs/spreads remain pending.

Eligibility and FX schemas validate evidence structure, not its authenticity.
Only trusted, verified catalogue/FX adapters should supply them. Tests use explicit
fixtures; no live broker catalogue or FX integration is claimed in this increment.
