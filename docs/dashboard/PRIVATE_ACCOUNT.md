# Private Trading 212 account mirror

Read-only live Invest account observations, not scanner paper results. Uses GET account/summary, positions, orders and history/orders. Requires account, portfolio, orders:read and history:orders scopes. No order write/cancel API code. CFD/Robinhood unavailable here.

Data exists only in collector memory and signed HTTPS delivery to /api/public/account/ingest. Never write raw balances/orders to Actions logs, artifacts, GitHub files or Telegram. Collector exceptions print allowlisted codes only. No AI request or cost.

Dashboard storage is owner-bound RLS, separate from research viewer permissions. Explicitly bind the nominated dashboard user to private_account_snapshot.owner_id before enabling repository variable ACCOUNT_SYNC_ENABLED=true. Empty owner rejects delivery. Account fingerprint cannot silently switch to another broker account. Only service_role executes the storage function; anonymous and shared viewer reads are denied. Do not enable before checking this binding.

Snapshots include up to 50 history pages / 2,500 items. history_complete=false explicitly marks a partial history; no inferred totals or win rates. Broker summary all-time realised P/L is distinct from the history window. Partial fills retain fill IDs and order IDs. Net EUR wallet impact is supplied by the broker, never quantity multiplied by a guessed FX rate. Requested order values retain native currency. Snapshot replacement never treats stale data as empty balances. This first version mirrors current API history, not an independent accounting ledger; broker exports remain authoritative.

Schedule follows weekday 08:00–23:00 Dublin scope with no out-of-hours override for ordinary runs. Separate job failure never blocks the research collector. Authentication or scope failures require updating the existing repository secrets privately, never pasting credentials in chat.
