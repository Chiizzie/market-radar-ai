# Research history, exposure and operational evidence

This reporting milestone preserves both existing strategy protocol hashes and all entry, exit, risk and spending rules. The original scanner is unchanged. There are no new model calls, trading alerts or broker-order operations.

## Historical evidence

Each close publishes a complete per-setup projection before its daily summary. Details live in a separate, deterministic `research-views-v1` partition so earlier workers can still replay their original event partitions. Snapshot IDs bind protocol, day, report time and all rows. Retries preserve event timestamps and hashes. The summary links one immutable snapshot; partial writes never advertise complete details. More than 2,000 setups is explicitly marked beyond detail capacity, without truncating aggregate statistics.

The dashboard shows the newest report per day and protocol, in pages of 30 dates, with 100 setups per page. It rejects mismatched, duplicate, unordered or incomplete snapshots. Older summaries remain readable but do not acquire invented detail records. Synthetic fixtures are for offline tests only.

## Paper exposure

Code-only, AI-reviewed and AVWAP arms are alternative experiments, not allocations to add together. Each reports open entry capital including estimated round-trip costs, initial risk to the original stop, pending watch capital, possible unresolved exposure and peak concurrent capital/risk/count. An observed close releases capital before new entries at the same timestamp. Instant round trips consume one allocation; their ordering relative to one another is not known. Unresolved exits remain potentially exposed. These statistics are neither a capital constraint nor a portfolio-return calculation; no sector correlation or slippage model has been added.

## Operational evidence

`deploy/scanner-health.yml` reads only the latest 20 main-branch scheduled workflow runs and jobs from GitHub. It publishes bounded, whitelisted metadata without model/provider/order/Telegram calls. The health panel always shows current evidence, regardless of the historical day selected. It distinguishes missing dispatches, an old monitor, unavailable metadata, incomplete job details and reported failures. Twenty minutes is the freshness threshold in the weekday 08:00–23:00 Dublin window. AVWAP observation monitoring uses New York session times. These configured weekday windows are not exchange-holiday calendars.

Recovery upload receipts are written only after GitHub confirms a matching, nonempty, unexpired artifact from a main-branch run. Receipts include the source event count and archive manifest checksum. They establish upload confirmation, not continuous availability or a restore test of that archive. Missing receipts become due at 22:30 Dublin for comparison and 16:30 New York for AVWAP; activation starts 7 November 2026. The existing separate storage-verification workflows test signed writes, idempotency and projection recovery without inventing trades.

## Deployment order

1. Rehearse and apply dashboard migration 0008, preserving viewer RLS and private raw evidence.
2. Deploy the validated signed endpoint and dashboard readers.
3. Pin the collector, reviewer, watcher and AVWAP worker to the tested source commit; preserve the account-sync pin.
4. Install the operational-health workflow, and run both real-cohort storage/recovery verifications.
5. Check actual health reports and history reads. Empty market cohorts remain empty; successful infrastructure checks are not trading performance.
