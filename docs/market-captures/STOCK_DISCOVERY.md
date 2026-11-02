# US stock directory discovery

Run `python -m market_radar_ai.market_data.providers.stocks --output artifacts/stock-directory.json`.

Source specification: https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs

The adapter fetches Nasdaq-listed and other-exchange-listed directories over HTTPS. It validates headers, row structure, flags, unique source identities and the completion footer. Requests have timeouts, redirects are rejected and each response is capped at 5 MB. Failures are recorded; if either file fails the usable stocks list is empty, preventing accidental partial replacement of a complete universe.

This initial subset excludes ETFs, test issues and punctuation-bearing/long symbols requiring explicit price-provider mapping. Exclusions remain visible. A simple symbol is only a candidate for Yahoo lookup, not confirmed provider identity. Other security types may remain; no common-stock-only claim is made. The file creation marker is retained but not yet interpreted for freshness, so automatic replacement of the persistent scan universe is deliberately not enabled. Validate catalogue age and instrument identity before promotion.

This is US exchange-directory coverage, not all global equities, European listings, OTC markets, or a broker account catalogue. Broker eligibility remains UNKNOWN. The directory is not a quote feed and does not establish liquidity. Live connectivity for this new adapter has not yet been verified.

Next integration: verify actual directory downloads, parse/validate file timestamps, resolve symbols and instrument types, then populate the persistent queue while retaining exclusion counts. Independent crypto discovery remains in the existing Kraken catalogue adapter.
