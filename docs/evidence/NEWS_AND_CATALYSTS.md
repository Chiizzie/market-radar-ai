# News and catalyst foundation

Implemented: typed source evidence, bounded Alpha Vantage NEWS_SENTIMENT adapter, provenance, publication/retrieval timestamps, duplicate-URL filtering, stale/future rejection and explicit partial/error/not_configured states. Source: https://www.alphavantage.co/documentation/#news-sentiment

Call `NewsProvider().fetch(symbol='MSFT')` from the backend, optionally omitting the symbol for broad news. Credentials come only from server-side ALPHA_VANTAGE_API_KEY. One GET per call, no retries, maximum 50 input items and 2 MB response. The default relevance window is 24 hours, not a guarantee of actionable freshness. No full article text is stored. Provider symbols such as CRYPTO:BTC are not broker or Kraken pair identifiers.

No account entitlement, credentials, subscription price or live connectivity has been verified. No subscription was purchased and no live news request was made for this change. Missing configuration returns not_configured rather than synthetic news. API rate-limit or entitlement responses without a feed return error. Request URLs/exceptions are never logged, avoiding key leakage.

Provider-reported relevance and news are not independently confirmed facts. Sentiment is deliberately not used as a trade score. An article does not establish an upcoming event date: event_at stays absent unless independently supplied. The news module is connected to the dashboard export; agent prompt integration remains pending. Trade authorization always remains false.

The evidence model also supports scheduled_catalyst and investor_disclosure. These are schema support only: neither has a live collector yet. Disclosures keep event_at (transaction time, if known) separate from published_at and retrieved_at. They must never be described as contemporaneous trades, endorsed investors or proof of successful trading. Unknown transaction time remains null.

Next: choose and verify a usable news entitlement or public issuer feed; preserve provider item IDs and entity mappings; add issuer/event calendar and disclosure collectors; connect a versioned evidence export to the six-agent inputs and Lovable. News ingestion alone does not remove broker eligibility, risk, currency or time gates.

## Credential-free macro source

`python -m market_radar_ai.evidence.public_feed --output news.json`

The Federal Reserve Board RSS adapter uses its official all-press-releases feed, listed at https://www.federalreserve.gov/feeds/feeds.htm. This supplies macro announcements only, not company-news or investor-trade coverage. It keeps titles, publisher links, publication/retrieval times and no invented ticker associations or future event dates. The seven-day retention window is historical context, not intraday freshness approval. XML declarations/entities, unexpected domains, malformed/future timestamps and oversized bodies are rejected; duplicate links and stale rows are counted.

Local validation: 219 tests passed. A live local request on 2 November returned public_feed_unavailable and zero items; no successful connection is claimed. The manual discovery workflow now collects news.json as a separate diagnostic artifact. Its step is non-blocking for the price rehearsal: inspect news.status explicitly; a green price pipeline does not establish news availability. No automatic schedule or paid call was enabled. The dashboard exporter now consumes this feed; agent integration remains pending.

## Dashboard evidence contract

The dashboard exporter accepts optional `--evidence news.json` and adds `evidence` schema 1.0. It distinguishes not_connected, not_configured, error, ok, partial and stale. A feed retrieved over 15 minutes ago becomes stale. Publication age is recalculated; intraday_recent means only publication within one hour, not verified relevance or a trade recommendation. Source URLs, titles and times are allowlisted; unknown fields are dropped. Failed feeds expose no articles. Successful empty feeds remain distinct from unavailable feeds. The manual discovery workflow re-exports dashboard.json after collecting news.json. Global snapshot expiry still applies. The frontend must also recheck ages over time.

Investor disclosure and scheduled catalyst support remains schema-only. This change does not populate agent inputs, verify broker eligibility or enable trade calls.

## Company-news leads

The bounded Yahoo adapter uses the installed yfinance `Ticker.get_news(count=10, tab='news')` interface, inspected directly in this environment. It retains canonical article links, publisher names and aware publication times; rejects malformed/future/older-than-24-hour items; and removes duplicate URLs. The query ticker is metadata only: article symbols remain empty until entity relevance is verified. A query result is not an issuer announcement or a proven catalyst.

Command: `python -m market_radar_ai.evidence.company_news --symbol MSFT --output company-news.json`. This feed uses the existing optional market dependency, no new key or purchased subscription. Availability and completeness are not guaranteed. Live connectivity is not yet verified. The public-news verification workflow now probes it separately and preserves its status even when the macro feed succeeds. The imported evidence exporter can accept this file using --evidence; feeds are now combined; verified ticker matching remains future work.

## Combined feed

`python -m market_radar_ai.evidence.combine --feeds macro.json company.json --output combined.json`

Validates each input, preserves failed/stale source status in `sources`, deduplicates canonical evidence IDs, sorts by actual publication time, and caps output at 50 items. It preserves the oldest contributing retrieval timestamp; aggregation never makes old evidence fresh. No usable feeds returns error, not empty success. The news workflow now exports combined evidence to dashboard.json and keeps individual source files plus combined-news.json for diagnostics. The dashboard receives aggregate partial/error status; detailed source status is currently in combined-news.json, not rendered by the UI.

## Verified combined run and company-news limitation

GitHub run 41531863411 completed and exported two macro announcements plus zero company articles for MSFT. Combining and exporting worked; useful company-news delivery did not become verified. Inspection of the installed yfinance wrapper showed missing upstream response structures can become an empty list. An empty result is therefore now partial with availability_note=empty_response_unconfirmed, not an unqualified healthy feed.

The workflow runs all evidence parser/combination test modules and writes news-readiness.json. This acceptance check requires retained items from each source and current retrieval, separately from job completion. It is non-blocking for artifact retention; inspect news_delivery_verified explicitly. Passing it would still not verify entity relevance, catalyst significance or trade readiness. No subscription or credentials have been added.

## Direct issuer-feed probe

The public feed command now supports `--issuer` for the fixed Microsoft Source RSS URL https://news.microsoft.com/source/feed/. It uses the same size/XML/date/duplicate validation with Microsoft-only article host validation and scope SINGLE_ISSUER_EDITORIAL_NEWS. It is an issuer editorial source, not a comprehensive earnings feed or independent corroboration. Symbols remain unmapped. The combined workflow probes it independently and preserves its status alongside Yahoo and macro results. Runtime probe 41532330605 returned an error with zero retained issuer articles; delivery has not been verified. No claim of full company coverage is made.

## Delivery diagnostics and acceptance

Live run 41532330605 retained two Federal Reserve articles, zero Yahoo MSFT articles, and zero Microsoft Source articles with a provider error. Its successful workflow conclusion is not a successful company-news acceptance result. No live news is yet passed to paid agents.

Failures now expose only bounded reason codes and HTTP status: transport_error, body_read_error, redirect_not_followed, http_error, response_too_large, or invalid_feed. No response body, redirect location, exception text or request credentials are logged. Redirects remain disabled. These codes distinguish connectivity, redirects and parser failures without weakening the feed validation.

Combined source metadata includes validated_item_count. Delivery acceptance uses that count rather than raw input length. The workflow emits separate Yahoo and direct-issuer readiness files and a job summary so macro success cannot hide either company's missing delivery. Diagnostic steps remain non-blocking to preserve artifacts; check the explicit acceptance result. Local validation for this change: 236 tests passed.

Next acceptance milestone: retain real company articles from a verified feed, establish issuer-to-symbol mapping, then assemble dated evidence packets for the six agents. Unknown broker eligibility must continue blocking any actionable plan. Hosting/authentication, account eligibility, live agent evidence integration, scheduled catalysts and investor disclosure collectors remain separate unfinished work.

### Follow-up live result

Run 41534279083 on commit 9daf1dd2722c73742d4bdec104072fa977832fba confirmed HTTP 403 for the Microsoft feed from GitHub's runner. This is an access response, not evidence of an RSS parser defect. Yahoo again retained zero articles; Federal Reserve retained two. Both Yahoo and issuer news_delivery_verified results were false. The focused evidence suite passed 29 tests in that run. No access-control workaround or subscription was introduced.

## NVIDIA official publisher feed

The fixed registry now includes https://nvidianews.nvidia.com/releases.xml. One bounded request uses the existing strict RSS parser and allows only nvidianews.nvidia.com and blogs.nvidia.com article hosts. The registry attaches NVDA as a publisher-to-issuer association; this is not independent corroboration, broker eligibility, catalyst significance, or article-by-article investment relevance. Feed publication times are retained; modification times never substitute for them. Articles remain provider_reported. Seven-day history remains context, not intraday freshness.

Command: `python -m market_radar_ai.evidence.public_feed --source nvidia --output nvidia-news.json`. The legacy --issuer selects Microsoft; arbitrary URLs are not accepted. Local live retrieval retained seven articles and rejected thirteen; the combined/dashboard export preserved all seven NVDA associations. Local suite: 238 passed. The GitHub workflow now probes NVIDIA separately, combines it with the other feeds, and produces nvidia-readiness.json. Runner verification subsequently passed: run 41534972875 retained seven NVIDIA and two Fed articles, combined nine, and reported NVIDIA news_delivery_verified=true. Yahoo remained empty and Microsoft returned 403; their failed acceptance remains visible. The focused runner suite passed 31 tests.

Apple Newsroom was also inspected but not added: its feed exposed updated times, and the inspected article's structured publication date lacked an exact time. Those were not converted to fabricated intraday publication timestamps. No subscription, paid AI call, or access-control bypass was introduced.

The manual discovery-to-dashboard rehearsal now also collects NVIDIA, combines it with the macro feed, and exports the combined evidence alongside prices. Its YAML was checked locally; this updated manual workflow has not itself been executed. Existing live verification covers standalone retrieval, combination and news-only dashboard export. No live-agent analysis or full-market news coverage is claimed.

## Dated news inputs for specialist research

`python -m market_radar_ai.agents.news_input --evidence combined-news.json --symbol NVDA --output nvda-research-input.json`

Creates a news-research-v1 packet with at most ten deduplicated, newest-first articles linked to the requested symbol. Each carries its exact source ID, title, URL, publisher and original publication/retrieval timestamps. Both the feed and individual article retrieval must be within 15 minutes; publication must be within seven days. Articles older than one hour are explicitly context-only. Unmapped articles are omitted. Provider-reported linkage does not independently establish significance.

This separate input carries explicit missing chart, broker and EUR risk evidence. It contains no fabricated broker expiry or trade plan and cannot validate as the paper-trade ResearchInput. Existing offline ModelGateway specialist interfaces can consume it; all six receive the same immutable packet independently. Source text remains untrusted data. This is a data connection and mock interface verification, not a live six-model analysis. No paid adapter is activated.

A failed refresh overwrites the output with status=blocked and input=null. The news verification and manual discovery workflows now preserve this packet as an artifact. Local live NVIDIA retrieval produced a ready_for_research packet with zero model calls and trade_authorized=false. Tests cover stale/future/unmapped evidence, item freshness despite a new envelope, deduplication, bounds, injection-like text remaining data, six independent gateway requests, and rejection at the paper-plan boundary.

## Combined price and news research input

`python -m market_radar_ai.agents.combined_input --capture capture.json --evidence combined-news.json --symbol NVDA --output combined-input.json`

The combined-research-v1 packet joins one matching stock capture to the dated news packet. It verifies the capture checksum and original quality status, then independently validates retrieval age, OHLC values, source/symbol identity, a single native quote currency, chronological completed five-minute candles, duplicates and gaps. Requires 2–60 candles, retrieval within 15 minutes and a latest candle within 15 minutes. No timestamps are refreshed to hide old data. USD remains USD; no EUR conversion or indicator/entry/stop/target values are invented.

A separate market citation hashes the validated market block. Saved packets revalidate evidence and citation consistency. The packet remains research-only with missing broker eligibility, EUR risk/plan and catalyst significance. It cannot pass the paper-plan input boundary. Failed CLI refreshes write blocked with input=null and zero model calls.

Local validation: 266 tests passed, including six independent mock assessments, six rebuttals and final adjudication retaining all unresolved objections. This is protocol verification, not paid AI reasoning. The public-news workflow now performs a bounded one-symbol NVDA capture and preserves combined-input.json, including blocked results. The manual market rehearsal also attempts composition when NVDA appears in its selected batch; absence correctly blocks that packet. Live combined readiness is pending verification; a successful workflow is not evidence freshness approval.

## Metered research orchestration (not activated)

`agents.live_research.run_research` accepts a combined packet and the existing OpenAIPilot client only when explicitly enabled. It requires the shared GitHubSpendingLedger instead of a fresh scratch allowance. No workflow, schedule or CLI activates this path yet. Existing model/pricing and conservative per-call reservations are reused unchanged.

At most eight requests: six independent role assessments, one debate, one conclusion. Freshness is checked before the first and every subsequent request. Request IDs include the packet digest and stage; shared-ledger duplicate rejection prevents replaying a paid stage. An interrupted run does not automatically resume or retry. Unknown usage retains the reservation. Known usage is recorded before semantic response validation. Report state is atomically checkpointed; existing report files cannot be overwritten.

Responses must match the snapshot, specialist role and supplied citation IDs. Code retains every specialist concern and mandatory missing-data item outside the model's conclusion. Conclusions are restricted to MORE_RESEARCH_NEEDED or INSUFFICIENT_EVIDENCE; trade_authorized is always false. Citation membership does not independently prove the factual accuracy of model prose. Broker verification, risk plans, paper-trade approval and orders remain outside this module.

Tests use the actual pilot client and shared-ledger implementation with in-memory storage and stubbed HTTP: no provider calls or real charges. They cover the eight-request protocol, preflight and mid-run expiry, duplicate IDs before HTTP, malformed citations after accounting, and retained holds on provider failure. Live paid evaluation remains pending a current packet and explicit activation through a durable-budget runner.
