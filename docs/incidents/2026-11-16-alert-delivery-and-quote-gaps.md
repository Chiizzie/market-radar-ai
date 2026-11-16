# 16 November 2026: review notification failures and quote gaps

## Evidence before repair

The earlier strategy-routing input-capacity fix remains effective. Subsequent failures are separate:
- Review jobs in scans [43894347930](https://github.com/Chiizzie/market-radar-ai/actions/runs/43894347930), [43910970383](https://github.com/Chiizzie/market-radar-ai/actions/runs/43910970383) and [43912751179](https://github.com/Chiizzie/market-radar-ai/actions/runs/43912751179) reached the signed dashboard archive acknowledgement, then raised the generic `Paper Telegram delivery unconfirmed; do not retry`.
- The first two archived decisions were BCE at 15:17:33 and KVYO at 16:48:09 Europe/Dublin. Both real archives render correctly offline (1,044 / 1,045 characters). Their notification ledger entries remain reserved. The old catch combined rendering, HTTP send, acknowledgement validation and GitHub ledger confirmation, so neither the historical transport cause nor actual Telegram receipt can be inferred from the error. Do not replay these reviews or resend their notifications.
- Comparison watchers rejected stale IEX quotes: NAVN at 15:55 (34.974 seconds), MXCT at 16:15 (35.629), WLTH at 16:20 (45.368) and 16:35 (65.065). The 16:20 paper watcher had a 44.602-second WLTH gap. These recovered but exceeded the existing 30-second allowance. The 16:50 comparison run also ended with unresolved GERN/RAL gaps. Polling cadence remained healthy and valid quotes for other symbols continued. This is not evidence of an all-symbol collector outage.
- The 17:00 scan [43913754205](https://github.com/Chiizzie/market-radar-ai/actions/runs/43913754205) completed successfully. One successful run does not resolve intermittent failures.

## Narrow delivery repair

Source `bb3731f50a77972e547402f5c23e719e201ca973` is based on the exact deployed review source `dbafe2c37e52ecd43fa85f404abd53d069f15995`. Only the review job is eligible to move to it. Account sync, manual alert audit, routing and every observer/experiment keep their existing pins.

The code preserves known dashboard and Telegram acknowledgements separately from delivery-ledger confirmation. It writes delivery/status artifacts after a completed AI review even when notification delivery fails. Safe diagnostics record stage, bounded error category, HTTP status and numeric retry-after, never tokens, chat IDs, provider bodies or raw exception URLs. A confirmed Telegram acknowledgement can still supply the genuine manual timing clock if subsequent ledger confirmation fails. Reservations remain permanent.

One bounded in-process retry is allowed only for Requests `ConnectTimeout`, which means the connection was not established. Watch expiry is checked again before that retry. Read timeouts, other connection errors, HTTP errors, malformed or mismatched acknowledgements and confirmation failures never cause a resend. No historical reservations are cleared. References: [Requests exception contract](https://requests.readthedocs.io/en/latest/_modules/requests/exceptions/) and [Telegram request/response contract](https://core.telegram.org/bots/api#making-requests).

No model budgets, trade approvals, strategy protocols, quote ages, 30-second recovery allowance, paper-capital rules or original scanner are changed. Critical failures remain visible. This does not claim that stale IEX coverage is repaired or that historical Telegram delivery has been established.

## Verification

Local verification: 1,690 tests passed; compilation and diff checks passed. Tests cover pre-send timeout recovery, no resend after ambiguous errors, expiry during retry, provider rejection, invalid acknowledgement, persistent reservation, confirmed-send/unconfirmed-ledger separation, manual clock preservation, completed-review failure receipts and prevention of another paid review.

Both actual failed archives passed an offline transport-stub replay with zero model calls and zero messages:
- Run 43894347930 archive SHA-256 `6fe6b2095482ac85239b3fb175ee625c2fe08ebb911be9d1505b04acb1bb7fc6`.
- Run 43910970383 archive SHA-256 `0ec5a61b544f00e317c6cae57637dc63ee198f07ae8a863bf3aaa43eea7a93c4`.

Hosted verification: [43915423138](https://github.com/Chiizzie/market-radar-ai/actions/runs/43915423138). The isolated workflow runs the full suite and a credentialed read-only `getMe`/`getChat` check. It cannot send messages, call models or place orders. Its actual outcome and deployment receipt must be recorded below before claiming verified production recovery.

Hosted outcome: both jobs completed successfully. Offline job 133468128926 ran 1,690 tests and compilation on the exact repair SHA. Read-only job 133468664452 received HTTP 200 and validated `getMe` and the configured `getChat` at 17:10:58 Dublin (0.31 / 0.35 seconds). Current bot/chat access is valid; this does not prove sendMessage or historical receipt. Ordinary scheduled production verification was pending at activation and is recorded below.

## Production verification

Activation commit `bf04048187072279b0372dad897463c9b6c067a3` changes only the review runtime pin. Normal scan [43916423204](https://github.com/Chiizzie/market-radar-ai/actions/runs/43916423204), review job [133472504388](https://github.com/Chiizzie/market-radar-ai/actions/runs/43916423204/job/133472504388), checked out the exact repair SHA and completed successfully. The COP decision was NO_ACTION because entry gap and reference spread exceeded their unchanged 20-bps checks. Its eight model calls belonged to the ordinary authorized schedule, not a diagnostic rerun.

The archived receipt confirms dashboard delivery, Telegram acknowledgement at **17:18:28.357852 Dublin**, one send attempt, and confirmed notification ledger. No manual watch clock was fabricated for this NO_ACTION decision. Artifact 14250111675 has SHA-256 `5bf626477da0fa9397bbf2b1d020069a3d5e1f53972842c6a31fd847f7488ec4`; the downloaded bytes matched that digest. This proves the deployed delivery path works on a real run, not that intermittent historical failures are retrospectively diagnosed or eliminated.

At the verification snapshot, collection, routing, account sync, review and paper watcher had passed. Longer comparison/entry/method/strategy observers were still running: do not label the whole scan complete. Current readiness/execution reports (seq276687/276241) passed the evidence helper with actual evaluation time 17:15:42, input ages 181/306 seconds, 11 operational passes and one pending scanner-jobs check. Broker costs and some outcomes remain unverified; operational repairs do not establish trading profitability or live readiness.

[Machine-readable deployment evidence](../evidence/alert-delivery-repair-20261116.json) retains the exact pins, tests, run, artifact and receipt. No historical notification was resent, no allowance was increased, no quote threshold was weakened, and no order was placed.
