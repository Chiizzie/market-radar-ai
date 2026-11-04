# Scheduled six-agent research decisions

The weekday collector now has a separate decision job. It uses the existing ranked, symbol-independent evidence packages: six independent paid specialist responses, followed by debate and a final conclusion (eight calls). It is not restricted to NVDA. Collection holds no OpenAI credentials and its job concurrency is separate, so a long review does not block the next capture.

## Admission and costs

Only the exact main scheduled-scanner workflow, first workflow_dispatch attempt, Monday–Friday 08:00–22:00 Europe/Dublin, may invoke scheduled review. Explicit out-of-hours verification never invokes models. Unknown credentials, stale evidence, invalid scope or unavailable durable state stop the process. Source/role/citation validation remains enforced.

A compare-and-swap marker on state/ai-budget permits one stock and one crypto review per Dublin date, at most 16 generation calls per day. Markers survive failure, restart, lost responses and workflow reruns; there is no automatic paid retry. Candidates follow the existing shortlist ranking, stocks first. A market with no candidate does not consume its quota. Existing monetary caps remain EUR 0.50 daily, EUR 10 monthly and EUR 1 lifetime. At least EUR 0.15 headroom is required before starting; actual per-call reservations enforce the hard caps. The headroom check is not a promise that all eight calls will fit. Unknown charges remain reserved. No budget history is reset.

## What the result means

Artifacts include the original package, eight model responses, usage, deterministic decision.json, signed dashboard archive and receipt. The existing Candidate research archive receives the real reviews without a frontend rebuild. No Telegram messages are added by this connection.

Research verdicts are REJECT, WATCHLIST or MORE_EVIDENCE_REQUIRED. Every result remains NO_ACTION because this research contract supplies no verified EUR trade plan or execution admission. An optimistic model cannot waive that. Completed reviews remove only the review-not-run diagnostic from the decision summary; original package gaps remain auditable. Expired reviews are explicitly historical. No live orders exist.

This milestone does not complete actionable trade calls: generic EUR plans reviewed by the agents, account-specific broker eligibility, executable prices/costs, catalyst verification and final admission still need connection. The old NVDA plan rehearsal is not silently reused for other symbols.

The current momentum shortlist requires 20 completed five-minute bars. Stock context is collected earlier, but this job does not yet run paid premarket/context reviews or their separate dashboard contract. Do not promise a stock decision at the opening tick. Coverage is the collector's requested universe, not every listed stock.

## Verification

807 local tests passed before deployment, including the new weekday/DST/scope gates, durable quota, lost-write behavior, budget headroom, archive validation and one-complete-cycle/no-second-model-call integration test. Live model completion and dashboard delivery must be verified from the subsequent production run, not inferred from these tests.
