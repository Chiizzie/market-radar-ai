# Account history and delivery failures — 23 November 2026

All times are Europe/Dublin. Inspected main `c24acb9bf4e0580e7d7fba4ee1d1af6adbb45a46` and the workflow's actual runtime pins.

## Evidence

- Ordinary runs 45194950197 (14:30), 45195791489 (14:35), 45196701407 (14:40), and 45197584116 (14:45) failed in account-sync only. All four logs report `order_history`, `account_read_transport_error`, one retry. The approximately 56-second elapsed time is consistent with two 25-second read timeouts plus five-second backoff; the sanitized logs do not prove the underlying exception type or a provider-wide outage.
- Fresh scanner snapshots continued arriving: the 14:45 capture was stored at 14:46:02 and the 14:50 capture at 14:51:16. The last account snapshot at initial inspection was generated 14:25:33 and stored 14:25:47. Account sync failure also prevented that cycle's holding review from running.
- Friday 20 November had ten distinct failed ordinary runs: six comparison quote-quality failures, one package-install broken pipe, one artifact-finalization connection reset, one Telegram HTTP 502, and one dashboard connection error. These are separate from Monday's account history problem and Thursday's artifact metadata fix.
- Quote failures: 44778154354 (BSP), 44792577498 (NTNX), 44793432505 (stock validation unavailable), 44801948284 (HCA), 44803521093 (ARLO/GTX), and 44811200775 (YSWY). The workers still polled and preserved observations. Long or unrecovered gaps remain failures; quality thresholds are unchanged.
- 44748564510's hash-verified decision ZIP (`5eecbf1c1a7b515ffd6bc03d8600163a91b55ff762db0c27d33e1725cf349ba5`) records a confirmed dashboard archive and Telegram HTTP/provider code 502. No message replay or repeated model call is appropriate.
- 44817917273's hash-verified capture ZIP (`e30cc343f2554b5f5cab29313524d62b572e0d8eb772f7cc3698d3bbdd42c534`) records `connection_error`. Snapshot `7f27d1165fac1ada420888a79e779a563c9ce4748fd34e297fba9c771b4e6666` was generated at 21:11:05 but its database row was received at 22:49:55: this is expired historical evidence, not a timely acknowledgement.

## Changes

1. On a history transport failure, use the existing single retry to request 20 rows at the same cursor instead of repeating a 50-row request. Continue with the server's next-page cursor. This is a bounded mitigation, not evidence that Trading 212 has recovered. Preserve the existing overall retry/page limits, rate pacing and completeness flag. A failed retry still fails the import before delivery and leaves the prior private snapshot untouched.
2. Route snapshot connection errors through the existing signed, hash-matched receipt lookup. It performs one bounded read, never repeats the POST, and preserves original expiry and archive checks. An absent, mismatched, expired or unavailable receipt cannot enable timely review.

Tests cover history cursor preservation, continued pagination, exhausted retry, and receipt verification after a connection reset, including absent/archive/mismatched receipts and exhausted time. No strategy, quote-quality threshold, account risk, AI budget or broker execution setting changes.

## Remaining evidence

Verify an ordinary run using the new runtime pin, including its account-sync result and stored private snapshot timestamp. Provider-wide outage attribution remains unconfirmed. The earlier quote gaps and missing Telegram acknowledgement remain recorded honestly.
