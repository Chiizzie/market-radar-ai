# Wider stock capacity — 9 November 2026

Expanded technical screen from 300 to 1,200 stocks per cycle and detailed stock
research from 40 to 80. Discovery reserves one detailed slot for the existing
watchlist merge, so 79 may appear when MU already occupies a core slot. The
catalogue-wide lightweight snapshot pass remains roughly 5,700 names; detailed
coverage is not a claim that every catalogue name is technically checked.

Full-session IEX chart reads use batches of at most 100 symbols, four independent
HTTP sessions in flight, with one batch failure isolated from other batches.
Pagination remains bounded and incomplete responses are rejected. Injected test
sessions are serial. The full 1,200-symbol test made twelve batches, bounded
concurrency at four, and preserved 1,100 results when one batch failed.

Dashboard and backend contracts now agree on 1,200 technical checks, 80 detailed
stock rows, 30 crypto rows and 110 charts. The aggregate evidence ceiling rises
from 200 to 1,000 to avoid discarding source articles solely because the stock
batch doubled. Per-source limits, timestamps and 2 MB signed-ingest limit remain.
A synthetic maximum-capacity pipeline generated a 1,433,285-byte snapshot and
3,302,717-byte enriched capture, within the existing 2 MB / 4 MB limits. Arbitrarily
long evidence can still exceed byte limits and must remain an explicit failure.

The method observer accepts the wider research input but its 40-active-plan
capacity and existing protocol/risk definitions remain unchanged. Paid AI budgets,
entry checks and crypto collection are unchanged. Context research accepts 80
stocks plus 12 benchmarks. Historical cache-hit count supports 920 symbol-days.

These are tested capacity bounds, not proven live throughput or profitability.
After deployment inspect selected/usable counts, provider errors, collection time,
quote ages, delivery success and worker backlog. No synthetic fixture is published
to production. First live results remain pending at deployment.
