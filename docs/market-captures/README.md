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

## Stock-first dual-market milestone

The command now defaults to three stocks (MSFT, AAPL, NVDA) and two EUR crypto pairs (XBTEUR, ETHEUR). Override using `--stocks` and `--crypto`. Each market has its own bounded quota; duplicates are removed and unrequested/deferred instruments are never counted as covered. Per-request elapsed time is recorded separately from candle age. A successful download may still fail freshness or quality checks. Provider failures return a nonzero process status after saving the evidence.

A read-only GitHub Actions job captures these five symbols on manual workflow runs on the development branch and on the one-shot milestone commit. It has no AI or broker credentials, a five-minute job timeout, and retains the JSON as an artifact for 30 days. It does not schedule a scanner.

### Coverage target and remaining work

Stocks are the primary discovery market; crypto remains a separate supported market. These five samples are connectivity probes, not full-market coverage. Full coverage requires a maintained stock universe and broker-symbol mapping, broad quote screening, ranked candle retrieval with fair deferral, a freshness-aware cache, and measured provider capacity. The current five-minute bar adapters are insufficient to promise instantaneous executable prices. A future streaming/quote provider must be evaluated against exchange coverage, measured latency, subscription costs and usage rights before adopting it. No paid data subscription has been purchased.
