# Public market-data captures

Run `python -m market_radar_ai.market_data.capture --output capture.json` with the market extras installed. This bounded command requests MSFT five-minute bars from Yahoo Finance through yfinance and XBTEUR five-minute bars from Kraken's public OHLC API. It stores at most 60 bars per feed, native quote currencies, provider timestamps, Europe/Dublin capture time, quality findings and a SHA-256 checksum of each canonical payload. A checksum detects changed content; it is not independent proof of provider authenticity.

The capture is historical research evidence, never a live signal. Quality is assessed at capture time and must be reassessed before later use. Equity session boundaries can create legitimate gaps; gaps are flagged for review rather than silently repaired. FX conversion is not performed by this command. No account eligibility or news evidence is inferred from prices. Every record remains NO_ACTION.

## Verified run, 2026-11-02

`public-data-2026-11-02.json` preserves an unsuccessful connectivity attempt from the development environment. Yahoo returned a CONNECT tunnel 403; Kraken returned provider_retries_exhausted. Both contain zero candles and fail quality checks. This is a failure record, not a usable market replay fixture. Re-run from an environment with provider network access before evaluating agents on captured data.

Local software validation: 181 tests passed. No paid model requests were made for this milestone.

## Provider responsibilities

- Yahoo Finance via yfinance: stock OHLCV and the separate Yahoo FX adapter used for EUR conversion. This is not an execution feed.
- Kraken public REST API: crypto OHLCV and instrument discovery, including EUR pairs. Kraken prices are not Robinhood execution quotes.
- CoinGecko: broad crypto discovery, market capitalization and volume metadata.
- Trading 212: read-only instrument catalogue adapter, requiring credentials; authenticated connectivity remains unverified.
- Robinhood Europe: public supported-asset page, not an account-level eligibility or execution API.
- OpenAI: evidence analysis, not a market-price source. Previous six-role evaluations used fictional fixtures.

Next: obtain successful captures, add a sourced news feed and account-specific eligibility evidence, then evaluate the six roles on held-out research cases. No live-order capability is authorized.
