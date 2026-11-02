# Phase 1 — Market data layer

This branch is the isolated development branch for the independent Market Radar AI data layer.

## Scope

- Standardised instrument and OHLC candle schemas
- Public CoinGecko EUR market discovery
- Kraken OHLC candle adapter
- Yahoo Finance historical candle adapter
- Candle freshness, duplicate and interval-gap validation
- Transparent baseline momentum and relative-volume ranking
- Scan accounting for discovery, quality, shortlist and rejection counts

## Safety and operating boundaries

- Research and paper trading only; no live order placement.
- EUR is the reporting currency where conversion data is available.
- Provider timestamps and source identifiers must be retained.
- Invalid or stale market data must fail closed rather than produce a trade setup.
- AI agents are not connected in this phase; actual model costs will be measured before activation.

## Next steps

1. Integrate the provider adapters behind the project interfaces.
2. Add stock-universe discovery and supported Kraken EUR pair mapping.
3. Add FX conversion, retry/backoff, caching and provider health metrics.
4. Run live connectivity checks and record coverage limitations.
5. Expand automated tests before merging into main.


## Repository verification — 2 November 2026

- Imported the Phase 1 archive into `phase-1/market-data-layer`.
- Original repository-checkout suite: **8 passed**.
- Expanded suite: **18 passed**; compileall passed.
- Added CI for branch pushes and pull requests (remote outcome recorded separately).
- Fixed historical freshness false positives, empty-series validation, Yahoo missing
  currency/naive timestamps/forming bars, and invalid-loss/non-intraday risk bypasses.

## Live read-only provider checks — 13:48 Europe/Dublin

| Provider | Result | Returned data | Latest candle (UTC) |
|---|---|---|---|
| CoinGecko | OK | 20 EUR discovery instruments | n/a |
| Kraken | OK | 720 completed XBTEUR 5-minute candles | 2 Nov 13:40 |
| Yahoo Finance | OK | 390 MSFT 5-minute candles | 30 Oct 19:55 |

These are adapter connectivity checks, not full-market coverage or trade readiness.
Yahoo returned previous-session history before the US regular-market open; it must
not be treated as an actionable current quote. Raw smoke output is in
`docs/provider-smoke-2026-11-02.json`.

## Remaining gates

- Broker eligibility verification, broad stock discovery and crypto identity/pair mapping.
- Timestamped EUR FX conversion, bounded retry/cache/batch scheduling and health metrics.
- Session-aware freshness/gap policies and integrated screening quality gates.
- Six actual independent AI agents, debate, cost enforcement and accuracy tracking.
- Annotated charts, paper position lifecycle and automatic intraday exits.

No paid AI models, live orders, deployment, or merge into main is enabled.
