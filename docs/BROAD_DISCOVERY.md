# Broader discovery

The scheduled collector can enable `ENABLE_BROAD_DISCOVERY=true` and
`ENABLE_CRYPTO_DISCOVERY=true`. The original `market-radar` repository is independent.

| Stage | Stocks | Crypto |
|---|---|---|
| Universe | Persisted Trading 212 USD stock metadata | Current public Robinhood Europe support list |
| Light discovery | IEX snapshots for all catalogue candidates, 500 symbols per request | Public Kraken EUR tickers for verified identities |
| Technical observations | Up to 300 current-session histories, batches of 100 | Up to 30 completed five-minute histories |
| Detailed collection | Up to 40, including watched positions and MU | Up to 30, including watched positions |
| Selection | Activity, snapshot turnover/movers and rotating catalogue slots | Turnover/movers and rotating catalogue slots |

Half the preliminary capacity is reserved for catalogue rotation. Half the detailed
stock shortlist rotates among usable technical observations. Selection is research
ordering, never trade admission. IEX is a partial exchange feed; premarket collection
does not satisfy regular-session technical gates. The snapshot adapter rejects
stale trades and prior-session daily data. Historical bars follow bounded pagination;
an incomplete batch is unavailable, never a successful empty observation.

Crypto identities are explicit in `crypto_identities.py`, verified on 2026-11-06
against the public broker list and Kraken AssetPairs. Live catalogue name/symbol and
venue base/quote/wsname/internal-key/status checks remain mandatory. At verification,
94 of 97 broker assets had an exact EUR mapping; excluding USDC and EURC left 92
discovery candidates. Additions or renamings without a verified mapping are counted
as unmapped. This public catalogue does not establish account buying permission.

Reference-quote validation, exact publisher category matching, targeted post-review
refresh and paper observers use the same identity map. Common-word/short tickers
are not inferred from headlines. CoinDesk remains a single partial catalyst source;
missing symbol-linked news still blocks paper approval. Quotes remain independent
venue references, not broker execution prices. One bad quote is unavailable only
for its own asset; checksum, identity and clock guards still apply to every result.

The combined news limit is 200; individual publisher/article limits remain bounded.
Stock context uses two batched reads; company news has four workers and calendars
two. Crypto OHLC has two workers. No API subscription, hosting service, AI quota,
strategy admission threshold or risk limit is increased by this change.

`discovery_coverage` is an optional strict aggregate dashboard contract. Catalogue,
light quotes, technical checks, detailed selection, unavailable data and deferred
work are separate counts. The original `REQUESTED_SYMBOLS_ONLY` capture scope is
preserved, as are zero capture-agent reports and no-action rows. Watchlist symbols
outside the discovery pool count as detailed selections without inflating the pool.
Stored counts retain their observation time and historical snapshots remain labelled.

Individual data gaps remain visible and ineligible. A whole-market capture outage
fails the job. Transport-only discovery retries are limited to one; no stale crypto
catalogue fallback or paid data-feed fallback is introduced. Existing AI budgets,
eight-call review bound, paper-only mode and order prohibition remain unchanged.

Validation includes 300-symbol batch reads, pagination/fault isolation, crypto
identity/rotation, 40-stock + 30-crypto + 200-article pipeline capacity, expiry replay,
signed dashboard ingestion and actual offline CLI stages. Deploy the dashboard
contract before changing collector/reviewer/watcher pins; keep account-sync pinned
separately. Verify a naturally scheduled production collection before declaring the
larger universe operational.

Remaining work includes additional independent catalyst sources, richer strategy
families, measured queue revisit times, and enough observed paper outcomes to assess
performance. Broader coverage is not evidence of profitability.
