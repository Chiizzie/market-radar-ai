# 17 November: recurrent shared storage stall

All times Europe/Dublin. Status at 20:50: collection and account delivery remain unconfirmed; not resolved.

## Evidence

- 20:00 scan 44164710752 and 19:55 scan 44163724208 passed.
- At 20:05, strategy job 134331319420 in run 44165512314 failed with strategy_restore_capacity. Entry enrolment also failed.
- Downloaded failure journals establish the capacity failure was the 90-second restore deadline, not the 75 MB or 100,000-source-event cap: strategy 8,931 events / 13,512,972 bytes; entry 5,761 events / 11,758,688 bytes.
- By 20:25, collection job 134343042160 (run 44169097358) collected data but failed to confirm dashboard delivery. Its collection-failed Telegram is the user-reported notification. Paid review was skipped. Account and research jobs also timed out.
- Read-only hosted probe run 43954474101, attempt 4, job 134351381012: published HTML HTTP 200 in 0.817 s, but both signed research reads timed out after three attempts (37.581 s and 37.604 s). One cursor is above every safe integer sequence and should return no rows.
- SQL management reads are intermittent. Database size was 927 MB and postmaster start remained 2026-11-03T19:41:55.979084Z. No completed restart is established. Index catalog reads repeatedly returned UNAVAILABLE; this does NOT prove missing indexes.
- Activity samples did not establish a lock blocker. A later management query for an empty sequence range returned no rows, but this is not evidence that the signed application data path recovered.
- Provider public status reported Apple authentication issues; there is no evidence tying that incident to this storage failure.
- Hosting console inspection was blocked by the browser security policy in this session. No pause, wake, restart, session termination, paid upgrade or provider support message was performed.

## Deployed mitigation and cache repair

Commit e267285079100f0fe657aa74493fc2c92217c3ac:
- Method observation and manual alert audit do not launch after failed collection.
- Execution and shared manual portfolio workflow-completion triggers require successful trusted main scans. Normal timers and operational health remain enabled.
- Run 44172618037 confirms failed collection now skips method and manual audit; dependent runs 44172787623 and 44172787593 skipped the extra history rebuilds.

Runtime fixes:
- Strategy source 7a41b7da4a31ac8223b14ea5b7bf2fd06c71d67b, parent 5002a0e004b89bb9c17895fa6d19d5ce3ed236e6.
- Paired entry source 354a61581c8bffbe1b4210b9c971bc8fcf7be621, parent 1f777dff0d7ae883cc54e6657a0ece8807c57d09.
- An HMAC-authenticated, compressed daily checkpoint preserves the complete validated immutable event prefix. It includes reports, original event bytes, sequence gaps, receipt clocks and screening evidence.
- Prefix authenticity, digest, experiment/day, event count and sequence are checked before any projection mutation. Every restored event still passes the original domain validator. Invalid caches fall back to authoritative replay.
- After a verified page the checkpoint is saved atomically, including before a restore deadline failure. A later worker can resume the verified cursor. A new signed storage read is still mandatory; cached history never proves current service health or authorizes trading.
- Separate daily GitHub cache keys retain strategy and entry history. Entry enrolment retains its existing short lock; observers remain independent.
- No strategy/protocol, risk, quote freshness, budget, notification receipt or order-execution rule changed.

## Offline validation

Strategy suite: 1,580 tests passed; its sole workflow-file failure was rerun successfully with the actual deployment workflow (9 watcher tests passed).
Entry suite: 1,602 tests passed; two workflow tests failed because runtime source branches omit the main workflow. Retesting against the deployment workflow exposed an old test scanning subsequent jobs rather than only the observer; scope corrected. All 13 phase/watcher tests passed.
Includes authentication, truncation, wrong partition/key, duplicate/order/cursor, required live-tail read, and resumption after the 90-second deadline.

Exact failure-journal replay:
- Strategy SHA256 7b22d896a4424e65b67763efae11a9840fb7683e5ce0afd68cc7ec064224769d; 89 cohorts. Full restore: 11 reads / 13,504,041 event bytes. Cached restart: 1 empty-tail read / zero historical event bytes.
- Entry SHA256 beea4b52541c56a2d64f8af341820f88344c531360487820eebd108ce6d45e3a; 101 cohorts. Full restore: 9 reads / 11,752,927 event bytes. Cached restart: 1 empty-tail read / zero historical event bytes.
- All events, journal bytes, timestamps, source digests, quotes, screens and outcomes matched. These journals are partial failure prefixes; this does not establish full-session outcomes or live recovery.

## Still required

Inspect a completed natural run at the new pins. Verify fresh snapshot and account receipt timestamps and successful signed storage reads. Confirm cache restore/save receipts on a later restart. Do not declare recovery from a green HTML page or skipped jobs. Do not rerun ambiguous collection/review delivery or reset notification ledgers. The blocked prior database pause must not be retried through another mechanism. Provider diagnosis remains necessary if the data service stays unavailable.

## 20:55 update

Deployment a3aec0a1b75154d48e6b234d4c09cb82f91f3f59 is on main; a fresh file read confirmed both new source pins and all three checkpoint configurations.

Probe attempt 5, job 134357972033, succeeded at 20:50:20, but the two empty signed reads took 21.890 s and 17.170 s, so this is intermittent availability rather than normal performance. The 20:50 ordinary scan 44173478333 still failed snapshot delivery at 20:51:33 (job 134358504722); account sync also failed. Its paid review and downstream rebuilds skipped as intended.

The last snapshot verified through SQL at approximately 20:51 was generated at 20:21:05.859042 and received at 20:21:08.289643. A subsequent combined snapshot/account timestamp query returned UNAVAILABLE; no fresh account receipt was established. Do not treat this earlier snapshot as live.

## First deployed runtime check, 20:56

Natural scan 44174328022 runs deployment a3aec0a1b75154d48e6b234d4c09cb82f91f3f59. Entry observation job 134361505398 checked out the repaired source and reached the new cache restore step. Its first cache is correctly absent; the authoritative bootstrap read then failed with storage_timeout after three attempts at 20:56:08. No checkpoint could be created before the first successful page. Account sync and comparison also failed. The cache repair is installed and proven offline, but cannot make an unavailable authoritative store healthy or establish a complete live bootstrap. Provider-side recovery/diagnosis remains the blocker.
