# News and catalyst foundation

Implemented: typed source evidence, bounded Alpha Vantage NEWS_SENTIMENT adapter, provenance, publication/retrieval timestamps, duplicate-URL filtering, stale/future rejection and explicit partial/error/not_configured states. Source: https://www.alphavantage.co/documentation/#news-sentiment

Call `NewsProvider().fetch(symbol='MSFT')` from the backend, optionally omitting the symbol for broad news. Credentials come only from server-side ALPHA_VANTAGE_API_KEY. One GET per call, no retries, maximum 50 input items and 2 MB response. The default relevance window is 24 hours, not a guarantee of actionable freshness. No full article text is stored. Provider symbols such as CRYPTO:BTC are not broker or Kraken pair identifiers.

No account entitlement, credentials, subscription price or live connectivity has been verified. No subscription was purchased and no live news request was made for this change. Missing configuration returns not_configured rather than synthetic news. API rate-limit or entitlement responses without a feed return error. Request URLs/exceptions are never logged, avoiding key leakage.

Provider-reported relevance and news are not independently confirmed facts. Sentiment is deliberately not used as a trade score. An article does not establish an upcoming event date: event_at stays absent unless independently supplied. The news module is not yet connected to agent prompts or the dashboard. Trade authorization always remains false.

The evidence model also supports scheduled_catalyst and investor_disclosure. These are schema support only: neither has a live collector yet. Disclosures keep event_at (transaction time, if known) separate from published_at and retrieved_at. They must never be described as contemporaneous trades, endorsed investors or proof of successful trading. Unknown transaction time remains null.

Next: choose and verify a usable news entitlement or public issuer feed; preserve provider item IDs and entity mappings; add issuer/event calendar and disclosure collectors; connect a versioned evidence export to the six-agent inputs and Lovable. News ingestion alone does not remove broker eligibility, risk, currency or time gates.
