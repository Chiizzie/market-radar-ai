# Performance and reliability evidence audit — 18 November 2026

Status: initial read-only evidence audit, NOT a profitability certification. This branch is isolated from main. No changes to running jobs, model budgets, orders, or alerts.

## Evidence inspected
- Current GitHub Actions recent run list, 18 Nov: repeated successful scanner health, scheduled research collection, manual shared paper portfolio and execution/readiness jobs. One execution/readiness run at 14:07 UTC was cancelled; investigate whether superseded by concurrency before treating it as a defect. Some newer runs were still in progress. Green workflow conclusion is not evidence of quote freshness, fill quality, or positive P/L.
- `docs/experiments/volume-risk-cost-deployment.md`: first natural comparison run 43267450568 on 12 Nov recorded 15 matched cohorts, 66 polls, 159 quotes, zero error polls, no closed outcomes at the captured snapshot. Ten variant arms must not be aggregated as independent profit.
- `docs/experiments/entry-confirmation-v1.md`: frozen prospective ask-trigger vs bid-confirmed protocol, validation from 16 Nov. Historical five closed examples motivated design only; not an unbiased performance estimate. Matched-closed subsets have selection bias; report nonfills and missing outcomes.
- `docs/incidents/2026-11-13-runtime-reliability.md`: prior startup, storage, overlap and readiness failures repaired; active-session verification was explicitly outstanding at the documented checkpoint. Successful after-close run does not establish active-session health.
- `docs/incidents/2026-11-13-execution-history-capacity.md`: disk-backed SQLite replay addresses 50MB memory ceiling but still has 1GB/1M event bounds and workflow timeouts. Track source growth and checkpointing.
- `src/market_radar_ai/agents/paper_comparison.py`, `paper_outcomes.py`, `paper_tracking.py`, `execution/journal.py` and `execution/engine.py` are present, so improvements should extend existing journals rather than create an independent competing ledger.

## Audit findings and immediate priorities
1. **Profitability unverified.** Recover latest *closed* natural paper cohorts and trade evaluation reports; compute net EUR after spread, slippage, commissions, FX, and model costs separately. Do not substitute hypothetical or synthetic fixtures.
2. **Outcome completeness unverified.** Reconcile every candidate and alert with stable identifiers to rejected, not-triggered, open, closed, stale-data, and unresolved states. Never count missing as zero P/L.
3. **Current-session runtime unverified at metric level.** For a consecutive-session sample inspect actual quote receipt age, poll gaps, execution/readiness job conclusions, cache replay, worker overlap, and delivery receipts. Record each session's data completeness and downtime.
4. **Comparison validity.** Preserve frozen variants, compare common eligible cohorts, report attrition, fill rate, quote gaps, regime/time-of-day and uncertainty. Do not tune on validation sample or add variant P/L together.
5. **Data retention and scale.** Monitor event counts, raw bytes, replay duration, archival expiry and 1GB/1M hard limits; propose bounded checkpointing before saturation.
6. **Risk controls.** Keep paper-only/no broker order write, intraday cutoff, stale-data fail-closed and deterministic risk gates. User's €50 maximum loss is a ceiling, not default position risk.

## Next implementation milestones (acceptance criteria)
- **R1 Evidence extractor:** reproducible, read-only command to summarize most recent completed production run reports and durable event digests; output session coverage, failures, closed/open/unresolved and missing-data counts. Include fixtures/tests for cancelled/in-progress runs, missing reports and duplicate IDs.
- **R2 Trade identity and reconciliation:** one canonical trade/candidate identity across signal, approval, paper fill, holding review and exit; deterministic idempotent state transitions and an exception report for unmatched events.
- **R3 Performance report:** net expectancy, win rate, profit factor, drawdown, sample size, costs, participation, and uncertainty by strategy/market regime. Missing outcomes excluded with explicit counts. Compare baseline and frozen variants without lookahead.
- **R4 Prospective holdout:** freeze parameters before unseen sessions; include negative controls, fill/slippage sensitivity and regime splits; publish pass/fail gates.
- **R5 Promotion gate:** no real execution changes without separately reviewed operational and statistical evidence and explicit user approval.

## Explicitly not established by this audit
- No claim of a profitable strategy, verified historical win rate, or current portfolio P/L.
- No claim that all recent workflows passed or that every job marked success contained valid live market data.
- No deployment, paid API calls, live orders, strategy changes, or dashboard changes.

## Evidence still needed
Fetch latest execution/strategy report artifacts or authenticated dashboard exports, inspect run jobs and logs for exceptions, reconcile durable source-event digests, and calculate performance only from observed completed paper outcomes.
