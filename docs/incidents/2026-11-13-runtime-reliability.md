# 13 November 2026: storage, startup and experiment queue repair

Deployment and first natural run verified on 13 November, completed 21:17:12 Europe/Dublin. Active-session observation remains a separate check.

## Observed failure mechanisms

- Comparison run 43502181018 spent 82.395 seconds reading 47,856 events across 49 pages; total startup was about 82.60 seconds. The CHYM quote gap remained a real feed problem, not repaired history.
- Method and context jobs in that run raised the old generic comparison_storage_unavailable exception. A timeout alone does not establish that a write failed; all stored evidence is retained.
- Entry run 43500609042 had a cancelled job with no steps. The serialized job held its lock through 330 seconds of observation plus setup, longer than the five-minute dispatch interval.
- Readiness inspected the last completed run and filtered out the independent comparison and experiment jobs, allowing an earlier success to hide current failures.

## Changes

Signed storage requests now retry transient read and append failures at most three times. Append retries use exactly the same immutable event bytes, IDs and original timestamps; only request authentication is refreshed. The deployed database function already uses a unique content-hash event ID and ON CONFLICT DO NOTHING under its partition lock. Permanent HTTP validation/auth failures and mismatched receipts still fail. Diagnostics disclose a bounded error code/status/attempt count without response bodies or credentials.

The comparison watcher can restore an authenticated raw-event prefix from the Actions cache. A domain-separated HMAC binds compressed bytes, experiment, day, count and cursor. Every event is replayed through the existing validators in a rollback-capable transaction; corrupt, incomplete or wrong-partition caches fall back to a full server read. The authoritative server tail must be read before polling. No cached quote is presented as newly observed. Bounds: 256 MB decompressed bytes, 300,000 events, 2 MB per line. Expired/missing caches affect speed, not completeness.

The short entry-enrol job retains the existing concurrency lock. Independent observe-only jobs run on each dispatch, overlap their 330-second observation windows and never enrol or change frozen plans. They retain the last actual enrolment screen and its timestamp. The protocol, both arms, five-second target, costs, risk and gap rules are unchanged. Source ordering and original database receipts remain authoritative. Active-session overlap and queue behavior still require a future-session observation because deployment follows the regular market close.

Readiness inspects the current dispatch and includes comparison and experimental failures; missing/running required jobs remain pending. The existing operations-v1 published schema is unchanged.

## Exact runtime revisions

| Runtime | Revision |
| --- | --- |
| scanner | `208f4bf5f9f1f403fb977075f0ea33912f4463b0` |
| entry | `1f777dff0d7ae883cc54e6657a0ece8807c57d09` |
| method | `889f1a110f9f7ac9d88dbbbc7e9548e8fe00f2c5` |
| context | `7a518a9b8e8450612a3291e716814c811eba4e67` |
| execution | `839af4f09abc6e7e21daa5bd41c56e587c96b25f` |
| strategy | `5002a0e004b89bb9c17895fa6d19d5ce3ed236e6` |

Collection/review/comparison use the scanner revision; execution/readiness and the operations reporter use the execution revision. Paper watcher/account sync remain 3a113a4e8c4e03e9b28799c146db1f1cae6f987a. Ledger maintenance remains 5ca5ffe1354729ddbbb735f8055fd0d50656f6d0. Dashboard remains 0210a0133233e0988fb6179c1d7d658d3d1701fb. Original market-radar is untouched.

## Verification

- [Runtime CI 43507049241](https://github.com/Chiizzie/market-radar-ai/actions/runs/43507049241): six complete runtime test suites and compilation passed, then read-only production recovery passed.
- [Entry follow-up CI 43507384567](https://github.com/Chiizzie/market-radar-ai/actions/runs/43507384567): 1,591 tests plus compilation passed at the final entry SHA.
- Production replay: 54,079 events / 48,762,175 bytes / 428 cohorts; cold server reconstruction 50.876 seconds, authenticated local replay 3.087 seconds, server tail 0.265 seconds. Prefix bytes and every report field match independent replay. See [machine receipt](evidence/2026-11-13-runtime-recovery.json).
- Tests cover lost acknowledgements after commit, immutable retry bytes and receipts, permanent errors, response mismatch, invalid HMAC/data/partition/order/semantic contents with rollback, exact cached-prefix plus server-tail equivalence, observer/enrolment isolation, preserved screens, and current failures overriding older success.
- One pre-existing strategy test used the old EUR5 lifetime fixture against the current EUR100 allowance. Its reservation is now derived from the configured limit; no allowance or spending code changed.

These are operational repairs. IEX freshness/spread limitations remain; SIP access, AI allowance, trading authorization and all risk settings are unchanged. No production history is deleted, rewritten or re-dated. Successful replay and tests do not establish live quote coverage, broker execution or profitability.


## Deployment and next observation

The runtime pins moved in commit 52a2920c7ffdbc95afe05a60dc5db11e05619b74 at 21:07 Dublin. [Deployed recovery run 43507778125](https://github.com/Chiizzie/market-radar-ai/actions/runs/43507778125) passed and seeded the main-branch cache. Its independent repeat verified 54,080 events / 428 cohorts: cold reconstruction 52.072 seconds; authenticated replay plus server tail 8.517 seconds. Prefix bytes and all report fields again matched. Timing varies by runner/load; do not report the 3.352-second branch result as a guaranteed latency. [Receipt](evidence/2026-11-13-deployed-runtime-recovery.json). Operations reporting completed successfully in run 43507824082, job 132169968887, using 839af4f.

The next active-session milestone is to inspect consecutive completed runs on 16 November or the next available session: authenticated warm startup below the existing 15-second warning boundary; no entry observer waiting on the enrolment lock; preserve actual missed/stale quote intervals; check fresh quote receipt coverage rather than green jobs alone. The frozen entry protocol already declares 16 November as validation start. Do not tune on commissioning outcomes, relax freshness/risk gates, or increase AI/data allowances to achieve a pass.

## First completed natural run

[43508253631](https://github.com/Chiizzie/market-radar-ai/actions/runs/43508253631), head 52a2920, completed successfully at 21:17:12 Dublin with all ten job conclusions successful. Comparison job 132171449937 restored the authenticated main cache: startup 6.109 seconds, first completed poll 8.704 seconds, 65 polls, zero storage/error polls, zero new quotes after market close. The largest internal poll gap was 5.490 seconds. All source data remained in the recovery journal. [Machine receipt](evidence/2026-11-13-runtime-natural-run.json).

The entry-enrol, entry-confirmation and strategy experiment worker steps were session-skipped, so successful job conclusions do not validate their active-session overlap. Updated context collection and method jobs ran successfully. Execution/readiness run 43507778121 also passed at revision 839af4f: 77,035 source events, 72,662,801 source bytes, 713 cumulative cohorts, restore verified, zero model calls. Readiness seq 253964 correctly reported current-run jobs pending at 21:13:27 while observers were running; it was received 21:13:35.830102. Execution seq 253959 as-of 21:10:48.835088 was received 21:11:33.868826. AI daily headroom remained EUR0.129096 against the EUR0.15 requirement.
