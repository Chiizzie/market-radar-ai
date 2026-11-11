# Ledger, notification and paper-review reliability — 11 November 2026

All times below are Europe/Dublin (UTC on this date). These changes repair operational failures and clarify the paper-review contract. They do not establish profitable trading performance or authorize live orders.

## Observed failures and lack of calls

- Runs 43022336825 (12:40) and 43054763198 (16:05) failed immediately after reserving zero-cost markers when the subsequent ledger read omitted that reservation. Other review runs failed on unconfirmed ledger writes. The previous implementation collapsed HTTP conflicts and ambiguous failures into one message, so the exact HTTP cause of every historical write failure cannot be recovered.
- Runs 43044781802 (15:05, BMNR) and 43056475343 (16:15, GOOGL) interrupted paid reviews during settlement. A charged response was not returned to the review audit when accounting failed. Missing historical usage must remain reserved unless exact usage can be recovered; this change does not invent receipts or clear unknown charges.
- Six completed reviews examined through 16:54 were all NO_ACTION: FIS, FN, ORCL, PHAT, VIK and CRDO. FIS failed team clearance; the other five also failed refreshed spread, entry-gap and/or EUR 20-risk checks. Review rationales included inappropriate demands for live-account permissions in a hypothetical paper decision and demands for future trigger confirmation before approving a conditional watch. These observations do not prove the rejected trades would have succeeded.
- Three of those six selected candidates (FN, ORCL and CRDO) already exceeded the existing 20bps spread limit before paid review. Previously the limit was applied at final validation/entry rather than spending selection.
- Collection runs 42983655257 (08:00) and 43053996474 (16:00) reported unconfirmed Telegram status delivery. The old error combined Telegram-response uncertainty with notification-ledger confirmation failure; it does not prove the message was absent.
- Comparison runs 43055615702 (16:10) and 43060596887 (16:40) recorded stale-quote polls and continued collecting but exited failed. Brief recovered source gaps need different operational severity from persistent gaps or storage failures.
- Run 43063020674 (16:55) also had a real Kraken provider outage: 30 crypto charts unavailable, but all 79 selected stock charts were current and stock review continued. Its review then failed on the old budget-write path. External data outages remain visible failures; they are not relabelled successful by this patch.

## Changes

1. GitHub budget and notification stores retain each acknowledged blob and its exact Git SHA for the next read. Network reads use a unique query and no-cache header, and cannot regress below confirmed entries. Every write still uses compare-and-swap. Only definitive HTTP 409 conflicts trigger bounded reread/re-evaluation; unconfirmed reservations never trigger a model call or message retry.
2. Paid responses and validated usage are saved before settlement. Exact usage receipts can reconcile costs without repeating model requests. Recovery never authorizes an interrupted review or a late trade. Lost historical responses remain unresolved.
3. Optional collection-status Telegram failures produce explicit warnings and receipt artifacts without replacing the actual collection result. Acknowledged Telegram sends with unavailable ledger confirmation are labelled separately and never resent. Real collection failures still fail.
4. Comparison gaps become warnings only when every failed observation is a missing/stale quote, every affected symbol has a later durably stored quote, gaps last no more than 30 seconds, error polls are at most 20%, polling gaps are at most 15 seconds, and no storage/capacity/invalid-quote failure occurred. All gap counts remain recorded; no quote or outcome is manufactured.
5. The existing 20bps spread check now also runs before spending selection, allowing another eligible candidate to be considered. Historical baseline enrolment and packet eligibility are unchanged.
6. Paper specialists explicitly distinguish simulation assumptions from live execution permissions, rolling VWAP from full-session VWAP, and a conditional entry from an already-triggered trade. Numerical risk objections must identify the contradictory input. Hard REJECT vetoes and deterministic entry/risk/freshness/exit checks remain in force.

The new prompt revision is `paper-scope-clarification-20261111-v1`, recorded inside each new immutable packet; spending selection is `pre-review-spread-v1`. The source and execution protocols remain unchanged. Aggregate AI results span prompt revisions and must not be attributed solely to this revision.

## Validation before deployment

- 397 relevant tests passed across the accounting, notification, paper-review, conditional-entry, watcher, comparison, replay and readiness paths, including 21 new failure-case tests. A lifetime-headroom fixture was made independent of the old EUR 5 cap.
- Replayed the production archive from run 43064257889: 26,165 immutable events, 98 cohorts, as of 17:03:32. Every event identity and historical packet validated; the reconstructed execution report exactly matched the published report. No model calls.
- A narrowly scoped live workflow verifies one clearly identified zero-cost budget marker (`storage-consistency-check-20261111-v1`), settlement, fresh read, and preservation of existing entries/limits. It receives no model or Telegram credentials.

Daily EUR 1, monthly EUR 10, lifetime EUR 100, EUR 20 planned loss, 20bps spread, 20bps entry-gap, intraday-only execution and the original scanner remain unchanged. Deployment verification and subsequent forward observations are required before claiming that the live failure rate or decision quality improved.
