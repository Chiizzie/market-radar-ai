# Stock routing, budget visibility and baseline audit — 9 November 2026

## Confirmed findings

20:40 successful run 42695168949 produced five paper-review-ready symbols: AVGO, AMD, ONON, NVDA and AMZN. ONON was selected but no model calls occurred because the daily allowance had EUR 0.079125 remaining. Daily limit EUR 1; settled estimated spend EUR 0.920875; held reservations zero. Review requires EUR 0.15 remaining. Provider account credit is separate.

21:25 run 42702307531 confirms calendar batching succeeded and market capture completed instead of timing out. Collection delivered in about 21 seconds, but Kraken requests failed and the crypto circuit opened. Stock candles were stale/empty after the regular close. Collection remained failed and review skipped. Closed-market stock inactivity must not be described as a missed regular-session opportunity.

## Changes

Collection exposes review_ready only after confirmed delivery, all required stages present, all non-market stages successful, no unrelated failure, and at least one current market record. Review and market-context jobs may proceed from this explicit output despite a market-data failure. Per-candidate qualification, fresh stock/crypto reference checks, trading windows and budget controls remain unchanged. Failed jobs and provider gaps stay visible. Missing outputs do not permit review.

Paper review writes budget-headroom.json and includes period-specific limit, spent, held and remaining amounts plus the reserve requirement and blocking period(s) in budget-deferred status. Diagnostics render these figures in the GitHub run summary. No budget increase, no new notification flow, no live orders.

Validation: full suite 1,348 passed before the final budget regression was added; focused final suite 77 passed including the new exact EUR 0.920875 spent / EUR 0.079125 remaining case. Runtime 1a4c9773827ae9605a5a1d8d862649715144bf43. Live partial-market continuation remains to be observed.

## Six simulated losses: interpretation and unresolved evidence

These are reference-quote code-only simulations, not broker orders or six AI approvals. Stored comparison report as of 20:42:55 includes:

| Symbol | Simulated entry Dublin | Simulated exit Dublin | Net EUR |
| --- | --- | --- | --- |
| TSLA | 19:53:54 | 19:53:59 | -15.03 |
| NVDA | 20:23:57 | 20:42:44 | -5.01 |
| BEN | 18:19:32 | 18:55:51 | -4.31 |
| AVGO | 20:34:10 | 20:38:26 | -24.88 |
| AVGO | 17:48:47 | 17:52:31 | -5.21 |
| NVDA | 20:28:38 | 20:37:41 | -5.96 |

Total exact report rounds to EUR -60.40. Four had AI no_action, two were unreviewed. The optional replay spread/entry-gap caps are not configured in this comparison protocol, though the EUR 20 planned-loss check is applied at breakout entry. A stop gap can exceed planned loss. The 4.7-second TSLA outcome and AVGO's large exit gap require source-quote/FX reconstruction; this audit has not established whether they were genuine moves or anomalous observations. Do not treat these six outcomes as validated strategy performance or proof that AI adds value. Preserve the historical protocol and records; any changed spread/gap admission policy requires a separately identified prospective experiment.
