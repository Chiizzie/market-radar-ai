# Remaining audit milestones — 10 November 2026

Times are Europe/Dublin. These changes cover the remaining replay, chart-window and performance-evaluation work after the top-three audit fixes. They make no live orders, increase no AI budget, and leave the original scanner unchanged.

## Comparison replay

The quote ingestion path decoded every full cohort evidence packet for every observation. An SQLite expression index now selects only the relevant candidate's immutable enrolment timestamps. Date comparisons remain timezone-aware Python comparisons; fractional-second precision is not compared lexically. SQLite maintains the derived index on migration, concurrent writes and rollback.

On the actual saved archive of 23,848 events, 23,516 quotes and 50 cohorts, local replay fell from 136.261 seconds to 1.213 seconds (112.29 times faster). A separate new-code repeat took 1.636 seconds. Complete comparison reports and lossless per-day exports had identical SHA256 hashes. These are local projection timings, excluding network and report generation; see `2026-11-10-comparison-replay-benchmark.json`.

Production execution artifacts now include `source-replay-health.json`, separating database read time from local projection time. This permits an actual runner measurement without paid model calls.

## Chart-window evidence

The new `contiguous_20bar_recovery_shadow_v1` diagnostic identifies a potentially usable latest 20-bar window only when an otherwise clean IEX history fails solely because of gaps outside that window. It requires original, completed, exactly contiguous five-minute bars, current-session bounds, fresh tail, correct symbol/source/USD identity and no duplicates or provider warnings. It stores the unchanged window, original timestamps and source/window hashes.

The live quality and strategy gates are unchanged. Opening strategies still require their complete opening history. This diagnostic does not establish a qualified trade: broker, catalyst, spread, cost, portfolio-risk and AI checks remain unevaluated. Descriptive momentum, relative volume and window VWAP are evidence for a later separately versioned strategy test.

Collection artifacts expose counts and symbols in `discovery.json` under `chart_quality_summary.window_recovery_shadow`. Exact bar evidence is in `discovery-selection.json` under each symbol's chart diagnostics. The prior count of 124 gapped histories with a contiguous tail is only a coarse count: those rejected raw histories were not retained and cannot retrospectively be validated by the new checks.

## Entry, exit and cost review

The free execution workflow now runs an offline evaluator against its exact exported source events and current execution report. It verifies source protocol, source hash and count, reuses original event validation, and saves JSON/Markdown evidence with the workflow artifact and job summary. It separates independent baseline setups from alternative capital-constrained portfolios, exposes duplicates and peak exposure, and reports unfilled/closed states, exit reasons, gross-before-flat-cost results, assumed costs and net results.

One explicit 15-minute stall-exit diagnostic remains retrospective research only. It retains the original entry/stop/target, requires a bounded fresh observed bid, refuses paths with material observation gaps, and is labelled hindsight-biased. It is not a live strategy or a forward performance result. A frozen rule needs later unseen observations before adoption. The date-specific performance review is saved separately; actual account trades and private account identifiers are excluded.

## What still needs later evidence

- Observe next-session replay startup and chart-window counts on real new captures.
- Reconcile instrument/broker costs; assumed costs are not verified fees.
- Evaluate stable, separately labelled strategies over later unseen sessions, including losses, missed entries and unavailable outcomes.
- Do not infer profitability or AI value from one day, a small matched-pair count or a faster successful workflow.

## Validation

181 focused tests passed across comparison integrity/startup, execution source binding and portfolios, chart diagnostics/discovery, qualification freshness, watcher reliability, stock checks and the new evidence evaluator. Both workflow YAML files parsed. The archive benchmark additionally verified exact complete-report and lossless-event-export equivalence.

## Deployed verification

Runtime `ac29968ae9f07721bc50fa485a35e136a202b367` was deployed by main commit `02afd3f7f3507576b324d4ea387ca472095c5529`. Collection, review, approved/comparison watchers, account sync and execution research use this runtime; the existing separate market-context capacity pin and method-shadow pin are preserved.

[Execution verification run 42926230245](https://github.com/Chiizzie/market-radar-ai/actions/runs/42926230245) completed successfully at 23:48 Dublin. All 23,848 source events and 50 cohorts were reconstructed with restore verification, zero model calls and no trade authorization. Source replay took 25.259 seconds in total, including database reads; projection processing took 1.949 seconds. The Nov10 partition alone used 20.566 seconds for database reads and 1.948 seconds for projection, versus the prior approximately 119-second projection measurement. Network/storage time remains a separate startup cost.

The new offline evaluator succeeded and its artifact's arm outcomes and exit-shadow analysis exactly matched the saved local performance review. Artifact `13812969406` includes `source-replay-health.json` and the JSON/Markdown performance review. Collection's new chart-window assessment is deployed for the next scheduled capture; a fresh regular-session shadow count remains unverified until new market data arrives.
