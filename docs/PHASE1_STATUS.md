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


## Local verification (2 November 2026)

- `python -m compileall -q src tests`: passed.
- `pytest -q`: **8 passed**.
- Tests cover immutable candidate snapshots, risk limits and Dublin-time intraday cutoff, candle freshness/gaps, and baseline screener ranking.
- Live provider connectivity has not yet been verified.
- The implementation archive is available separately; its source files have not yet been committed to this branch.
