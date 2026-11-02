# Optional crypto news integration

## Implemented

Crypto research can now combine Kraken EUR candles with explicitly coin-linked Alpha Vantage news. Supported associations are XBTEUR to CRYPTO:BTC, ETHEUR to CRYPTO:ETH and SOLEUR to CRYPTO:SOL. No relevance is inferred from headlines or unprefixed equity tickers.

The new crypto-research-v2 packet preserves original provider symbols, publisher, URL, publication/retrieval times, source IDs and older-news context classification. Full coverage is never claimed. Broker eligibility remains UNKNOWN; EUR risk/plan and catalyst-significance gaps remain mandatory. The existing candle-only v1 format and historical captures remain valid.

The manual runner uses the optional server-side ALPHA_VANTAGE_API_KEY secret. Without a key, it makes no news request. Errors, stale articles or absent exact associations preserve the candle-only packet and missing-news warning. The original source result is saved in news.json and status records unavailable, unusable or partial evidence. There is no subscription signup, secret creation or automatic retry.

Official reference checked 2 November 2026: https://www.alphavantage.co/documentation/#news-sentiment . NEWS_SENTIMENT supports crypto-qualified tickers and currently requires premium entitlement. An entitled backend key and a successful live request are necessary before claiming connected news. A connected ChatGPT app does not automatically provide credentials to GitHub Actions.

## Verified

- 360 local tests passed, including exact association, wrong coin/equity rejection, timestamps, provenance mismatch, immutable mandatory gaps, failure fallback, secret omission and all eight simulated research stages.
- Real local data-only rehearsal: ready_dry_run, XBTEUR, 60 candles, latest candle 2026-11-02T23:30:00Z, retrieved 2026-11-02T23:38:30.490510Z.
- News deliberately unconfigured in that rehearsal: news_evidence=unavailable and crypto_news_not_supplied retained.
- Zero AI calls, no trades and no budget increase.

## Not yet verified or complete

Live news entitlement/connectivity has not been tested. This is a bounded news integration, not full-market catalyst coverage. News items are provider-reported headlines and links, not independently confirmed causal explanations. Broad stock discovery, account-specific broker eligibility, EUR paper plans, secure dashboard hosting and outcome-based evaluation remain separate acceptance gates.
