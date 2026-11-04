# Dynamic stock discovery

Scheduled collection can enable ENABLE_STOCK_DISCOVERY=true. Two read-only Alpaca screener requests retrieve up to 100 most-active records and 50 gainers plus 50 losers. These are provider-selected leads, not a complete exchange scan or broker-approved instruments.

The deduplicated interleaved list supplies four leading names and four rotating names, changing every 15 minutes. Eight detailed captures preserve the proven AI output and provider workload bounds. Deferred symbols and selection reasons are recorded in discovery.json and collection-report.json. This is wider discovery, not simultaneous deep analysis of 200 stocks. Shortlist-specific caches cannot reuse another shortlist's news/calendars.

Sources older than 15 minutes, future timestamps, malformed symbols, HTTP failures and missing credentials are rejected. If both sources fail, the original eight names are used with an explicit fallback flag. Before market open, Alpaca movers can describe the previous session and are deliberately rejected as current leads. No full premarket discovery is claimed.

Broker checks currently remain NVDA-specific; generic account eligibility, broker executable stock quotes, costs, fresh EUR trade plans and exchange calendar verification remain outstanding. Discovery never grants trade admission. AI quotas and budgets are unchanged.

Provider documentation: https://docs.alpaca.markets/us/reference/mostactives-1 and https://docs.alpaca.markets/us/reference/movers-1 .
