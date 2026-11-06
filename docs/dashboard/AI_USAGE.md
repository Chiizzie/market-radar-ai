# AI usage summary

Scheduled collection reads the existing GitHub spending ledger with its repository token. It never reserves funds, settles records or calls a model. Every signed scanner snapshot now carries `api_budget`, using the `ai-usage-v1` contract. Older captures may still carry null.

The allowlisted summary contains status, EUR currency, source, read time, Dublin budget day and daily/monthly/lifetime totals. Each period reports settled and reserved micro-EUR, configured cap, remaining budget, completed model calls and unsettled reservations. Zero-cost workflow markers are excluded from model-call counts. Request IDs, response IDs, tokens, credentials and raw errors are never exported.

Amounts are scanner estimates based on recorded model usage and pricing/FX assumptions, not the provider's prepaid balance or invoice. Pilot totals include previous tests. Reservations remain held until settlement. The dashboard's available budget is the minimum remaining amount across all three limits.

A missing or unreadable ledger yields `status: unavailable` and `periods: null`; it does not block market collection or invent zero costs. Browser and ingestion validation enforce the same aggregate shape, arithmetic, period ordering and snapshot-time binding. The UI marks figures stale after 15 minutes or a Dublin date rollover and labels imported data historical. Trade gates and the 60-second capture expiry are unchanged.

Deploy the dashboard contract before advancing the collector pin: the old ingestion contract rejects non-null budget data. The existing signed viewer-only snapshot route and database require no new credentials or schema changes.
