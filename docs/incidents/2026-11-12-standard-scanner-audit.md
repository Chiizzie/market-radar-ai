# Standard scanner audit and repairs — 12 November 2026

Evaluation session: **11 November 2026**, Europe/Dublin. Audit performed 12 November. These results describe reference-quote paper simulations, not personal brokerage profit or executable fills.

## Yesterday's evidence

All 548 workflow records for the day were retrieved across six pages. The standard collection workflow had **180 dispatches: 134 success, 40 failure, six startup failures**. There were **174 stored dashboard snapshots**, received no more than 5.732 seconds after their generation timestamps. Three collection jobs failed; most red workflows concerned other components. The six startup failures contain no jobs; their cause was not established here.

The final daily comparison report (research event seq 85083) covers **347 setups across 197 symbols**. The exact seq/event/snapshot identity is recorded in [the evidence summary](../evidence/2026-11-12-standard-scanner-audit.json).

| Alternative simulation arm | Closed | Wins / losses | Closed net, assumed costs included | Other outcomes |
| --- | ---: | --- | ---: | --- |
| Code only | 13 | 1 / 12 | −€68.53 | 320 not filled; 14 unresolved |
| AI reviewed | 3 | 0 / 3 | −€35.21 | 2 approved but not filled; 9 NO_ACTION; 3 interrupted; 330 not reviewed |

AI closed rows: LRCX −€25.92, SLM −€5.53, MOS −€3.76. LRCX's recorded exit used an **8.73% reference spread**; SLM was also previously flagged at 0.23%. Historical records remain unchanged. The guarded quote policy deployed for 12 November rejects ambiguous wide-quote entries/exits prospectively. A flag does not establish that the quote was erroneous, and the old simulated loss is not an authenticated broker fill.

Only one matched closed policy pair exists for this day. Different admission clocks and unresolved observations prevent a reliable causal claim about AI value. These arms use independent hypothetical allocations, not a portfolio whose returns can be added.

Code-only non-entry reasons: 180 no observed eligible fill, 98 invalidated before entry, 42 trigger gaps beyond policy. The 14 missing exit outcomes retain uncertainty.

**Budget limitation:** by 17:43:53 Dublin, daily remaining allowance was €0.092205, below the €0.15 required to start a review. Settled spend €0.878877; unresolved reservations €0.028918. The last review began 17:42:56. Median completed review duration was 44.879 seconds. There were 248 later setup enrolments, which are not 248 proven trade opportunities. The daily app limit remains €1; monthly €10; lifetime €100. These figures are not the provider credit balance.

## Findings on trading quality

- Median planned stop distance for the 13 closed baseline simulations: **0.4372%**. Assumed round-trip cost: **0.40%**. Median assumed costs were **47.78% of total planned loss**. This leaves a difficult entry/target/cost problem; it does not prove that widening stops would work.
- On the 12 November 15:30 capture, the scanner examined 1,200 stock charts: 560 usable, 640 unavailable; 79 selected for detailed collection. The broker candidate pool was 5,722. Sparse IEX coverage remains a material limitation, not a catalogue cap of eight stocks.
- At 15:34, NVDA was examined and failed the relative-volume rule (0.522 against 1.5). The opening rule compares the last three bars with earlier opening bars, so fading opening volume can exclude a continuing rise. AMD was examined and also failed momentum/VWAP checks. These observations do not establish profitable rejected trades.
- Future strategy experiments should separately test same-time-of-day volume, volatility-aware stops/targets, realistic instrument costs, and fresh consolidated data. Freeze each variant and evaluate on later periods; preserve the current risk limits and all old results.

## Repairs completed

1. **Reuse already validated broker catalogue metadata in the review CLI.** The existing checksum, symbol identity and ten-minute original timestamp checks still apply. FX, quotes and market clock are fetched fresh. The previous CLI discarded this reuse path and repeated the account-wide metadata request just after collection. In the inspected run, pre-review reference refresh took about 103 seconds. This fix removes an unnecessary request; it is not a measured guarantee of 103 seconds saved.
2. **Restore full-universe routing diagnostics.** The actual discovery manifest was 4,625,840 bytes, larger than the generic 4 MB artifact read limit. This silently yielded zero mover explanations and false outside-catalogue labels. Only the discovery manifest now has a bounded 32 MB allowance; other artifacts retain 4 MB. Missing routing evidence is explicitly unknown. Replaying the same unchanged capture yields **319 movers/core rows**, including correct NVDA/AMD selection, with zero unreadable artifacts. Of these 319, 295 were not examined in detail; this is discovery-stage evidence, not missed profit.
3. **Bounded recovery for read-only account GETs, with safe failure diagnostics.** Retry only transient HTTP/transport errors, at most once per endpoint and twice across the import; respect bounded reset/backoff times. Authentication, redirect, malformed body and validation failures are not retried. No POST/notification/order retry was added. Logs include allowlisted stage/error codes only, with no holdings, balances, credentials or response bodies. The 12 November 14:40 account-sync failure was previously collapsed to account_sync_failed; its exact cause cannot be recovered retrospectively.

Strategy thresholds, AI prompts, budgets, original scanner, live-order settings and broker-paper engine are unchanged.

## Verification and deployment

- **99 focused tests passed**, including CLI metadata reuse, current quote fetching, a >4 MB discovery fixture, unknown routing evidence, account transport/rate-limit recovery, retry exhaustion, credential redaction and existing qualification/notification boundaries.
- [GitHub regression run 43251925658](https://github.com/Chiizzie/market-radar-ai/actions/runs/43251925658): successful at runtime revision [3a113a4](https://github.com/Chiizzie/market-radar-ai/commit/3a113a4e8c4e03e9b28799c146db1f1cae6f987a).
- Actual capture replay: [run 43248535495](https://github.com/Chiizzie/market-radar-ai/actions/runs/43248535495), capture artifact 13957547493 and decision artifact 13957812637. No paid model calls, notifications or broker orders were used for replay.
- The five ordinary runtime pins (collection, review, approved watcher, comparison watcher, account sync) are updated to the tested revision. Existing method/context pins remain unchanged.
- **Production verification completed:** [normal 15:55 Dublin run 43252970506](https://github.com/Chiizzie/market-radar-ai/actions/runs/43252970506), main revision [2033ce3](https://github.com/Chiizzie/market-radar-ai/commit/2033ce306af0cce60d594d76b7159905b2b6c888), finished successfully at **16:02:35 Dublin**. All seven jobs passed: collect, review, account sync, approved watcher, comparison watcher, method shadow and market context.
- Account delivery confirmed at 15:55:34. Dashboard snapshot `44639865b4200f0f3affb7689ab942f98aed33febce971872f0fa3a28bacb2b5` was generated at 15:56:22.291 and stored at 15:56:24.329.
- Production qualification inputs confirm `catalogue_source=same_capture_validated_metadata`, retaining the original 15:56:15.261 catalogue observation while refreshing references at 15:56:58.664. The reference refresh and qualification step completed in **3.715 seconds**, compared with the earlier inspected reference refresh alone taking about 103 seconds; this is one observed comparison, not a performance guarantee.
- The new production discovery report contains **446 movers/core rows** with no unreadable artifacts. This is a different capture from the 319-row replay above. Artifact digests were verified for capture 13960941298 and decision 13960416674.
- Review returned `no_qualified_candidate_zero_cost`: no paid model calls in this run. Both quote workers completed **66 polls without errors**; there were no active setups requiring quote observation. This run verifies the repair deployment and ordinary operation, **not a new approved entry/exit lifecycle or profitable trading**.

## Source notes

[Alpaca's market-data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) distinguishes single-exchange IEX from consolidated SIP and documents the entitlement restriction on fresh SIP data.
[Trading 212 rate-limit headers](https://docs.trading212.com/api/section/rate-limiting/response-headers) describe per-account limits and reset timestamps. No provider subscription or budget was changed.
