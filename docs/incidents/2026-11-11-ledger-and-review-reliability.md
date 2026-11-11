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

- 406 relevant backend tests passed across the accounting, notification, paper-review, conditional-entry, watcher, comparison, replay and readiness paths, including 30 new failure-case and quote-quality tests. A lifetime-headroom fixture was made independent of the old EUR 5 cap. Interrupted-review receipt recovery is also checked to append corrected comparison costs without creating a decision.
- Replayed the production archive from run 43064257889: 26,165 immutable events, 98 cohorts, as of 17:03:32. Every event identity and historical packet validated; the reconstructed execution report exactly matched the published report. No model calls.
- A narrowly scoped live workflow verifies one clearly identified zero-cost budget marker (`storage-consistency-check-20261111-v1`), settlement, fresh read, and preservation of existing entries/limits. It receives no model or Telegram credentials.

Daily EUR 1, monthly EUR 10, lifetime EUR 100, EUR 20 planned loss, 20bps spread, 20bps entry-gap, intraday-only execution and the original scanner remain unchanged. Deployment verification and subsequent forward observations are required before claiming that the live failure rate or decision quality improved.

## Production verification

- Deployment `e1ac569ecfdea3248dd071378e7e646d1e380739` pinned the operational jobs to runtime `82a1bea71b0c6781ad379267b9fd0205a3df7897` at 17:13. The original scanner and special context/method pins were preserved.
- [Live zero-cost ledger verification](https://github.com/Chiizzie/market-radar-ai/actions/runs/43065992805) passed. The marker settled to zero and a fresh store read confirmed it, with all previous entries and the EUR1/EUR10/EUR100 limits preserved.
- [Production reconstruction](https://github.com/Chiizzie/market-radar-ai/actions/runs/43065992655) passed with 27,103 events and 116 cohorts; archive restoration was verified. No AI calls or orders.
- The [first updated scan](https://github.com/Chiizzie/market-radar-ai/actions/runs/43066344862), 17:15, delivered 79/79 selected stock charts and 30/30 crypto charts. Account sync and market context passed. Its independent comparison watcher completed 66 polls and 220 quotes with zero errors.
- Its LRCX review used the new prompt revision, cleared all final checks at 17:19:26, and registered a conditional paper watch. All eight model stages settled: total 68,189 microEUR (EUR 0.068189), no outstanding holds for this review.
- The approved-trade journal recorded LRCX's paper entry at 17:21:57.761434, before its 17:22:26 expiry. It was an open simulation when verified; no realised outcome or profitability claim follows from this one entry. No real broker order was placed.
- A FIGS watch at 17:05:40 preceded this deployment. Its Telegram/dashboard delivery was confirmed and its inline watcher received 35 quotes with no errors. It expired at 17:08:40 with no eligible fill. Concurrent comparison observations remained below the entry trigger. It is not an executed trade and is not evidence for this patch.
- Receipt recovery appends a fresh comparison accounting event after settlement, including when the review failed. This corrects the cost view without replaying the AI, rewriting historical decisions or authorizing a trade.

## Dashboard compatibility correction and recovery

The new optional `prompt_revision` field initially failed the dashboard's strict packet schema. This was a deployment compatibility error introduced in this change, not an AI or accounting failure. The first updated review and its watcher succeeded, but archive delivery rejected the new field and the review job eventually failed. SLM's review at 17:28:55 also reached the old deployment during propagation.

Dashboard commit `40ceab430c0d9e2c1ca4f9fa21dead174de895e2` explicitly allows the one known optional revision. All signature, exact packet-hash, policy, expiry, risk, hard-veto and no-live-order checks remain. 45 dashboard checks passed, including the actual unchanged LRCX archive; the production build passed. The new parser was verified in the published client bundle and by authenticated ingestion.

- [LRCX recovery](https://github.com/Chiizzie/market-radar-ai/actions/runs/43068511502) succeeded on its second attempt after publication propagated. The first attempt returned 422 and stored nothing. The restored archive hash is `b828e991484e2b4d56bacb0057f1b5005eed94ccec2d4f1cf22c8ce4e6ebe243`.
- [SLM recovery](https://github.com/Chiizzie/market-radar-ai/actions/runs/43069409824) succeeded. The restored archive hash is `8fb0931977f08e53c21ba60ad20592c7969916d53cb771bca5390769422d97cf`.
- Both database rows were read back and matched their original packet identities and completion times. Recovery made zero model calls, placed no orders and sent no expired Telegram watches. It did not replay an entire scanner or change any original evidence timestamp.
- SLM's paper entry was observed at 17:31:01.257873, before its 17:31:55 expiry. No real-account fill is implied.
- Normal dashboard ingestion subsequently succeeded for MTCH's 17:33:37 and MOS's 17:38:33 approvals, without recovery. The live scanner uses runtime `bed07f89195e88376052dd68dda9e8c332df8cc3` including the diagnostics-only recovery-marker fix; execution-report quality diagnostics use `3f62f228e2197e20c3348a9b9155b503f809df34`.

The 17:30 run's review succeeded, but both quote watchers reported stale SLM observations around 17:35:37–17:36:02. The comparison worker recovered that source gap; its initial 16.16-second polling gap still exceeded the 15-second warning-only limit, so failure remained visible. Approved-trade watcher gap histories also remain visible even after recovery. Its recovery metadata now clears only after a validated same-symbol observation passes journal processing, without erasing error counts or changing severity. This is not an error-free feed claim.

## Material remaining limitation: reference-quote execution quality

LRCX's journal subsequently recorded a stop at 17:24:15.513063 and a simulated net loss of approximately EUR 25.92. The corresponding reference observation had bid EUR 206.4081476126836 and ask EUR 225.2536776686230: approximately 873.16bps (8.73%) spread. The previous normal observation was near EUR 217.2. This is evidence of a very wide reference quote, not proof of an executable broker fill or proof that the source quote was erroneous. Planned EUR 20 loss is not a guaranteed realised loss cap.

The offline performance report now checks exact receipt-time entry and exit observations, flags spreads above 20bps and missing/ambiguous fill quotes, and reports the maximum spread for each arm. It applies equally to wins and losses, never substitutes a nearby price and never rescales or deletes an unfavourable historical outcome. Seven focused tests cover these cases. Replay of production evidence as of 17:33:36 specifically flags LRCX's exit at 873.16bps while retaining its original outcome. This diagnostic improves interpretation; it does not repair IEX coverage or verify broker execution. Feed quality and prospective strategy performance still need evidence before any profitability conclusion.

[Production quote-quality report](https://github.com/Chiizzie/market-radar-ai/actions/runs/43070116063) completed successfully at 17:41. It reconstructed 29,245 events and 143 cohorts, verified archive restoration, and flagged the same LRCX exit at 873.16bps in its published evaluation artifact. Original outcomes were unchanged, with zero model calls and no trade authorization.
