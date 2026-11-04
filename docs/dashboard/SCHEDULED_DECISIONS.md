# Scheduled six-agent research decisions

The weekday collector now has a separate decision job. It uses the existing ranked, symbol-independent evidence packages: six independent paid specialist responses, followed by debate and a final conclusion (eight calls). It is not restricted to NVDA. Collection holds no OpenAI credentials and its job concurrency is separate, so a long review does not block the next capture.

## Admission and costs

Only the exact main scheduled-scanner workflow, first workflow_dispatch attempt, Monday–Friday 08:00–22:00 Europe/Dublin, may invoke scheduled review. Explicit out-of-hours verification never invokes models. Unknown credentials, stale evidence, invalid scope or unavailable durable state stop the process. Source/role/citation validation remains enforced.

A compare-and-swap marker on state/ai-budget permits one stock and one crypto review per Dublin date, at most 16 generation calls per day. Markers survive failure, restart, lost responses and workflow reruns; there is no automatic paid retry. Candidates follow the existing shortlist ranking, stocks first. A market with no candidate does not consume its quota. Existing monetary caps remain EUR 0.50 daily, EUR 10 monthly and EUR 1 lifetime. At least EUR 0.15 headroom is required before starting; actual per-call reservations enforce the hard caps. The headroom check is not a promise that all eight calls will fit. Unknown charges remain reserved. No budget history is reset.

## What the result means

Artifacts include the original package, eight model responses, usage, deterministic decision.json, signed dashboard archive and receipt. The versioned Candidate research archive receives real reviews after the matching v2 frontend compatibility update. No Telegram messages are added by this connection.

Research verdicts are REJECT, WATCHLIST or MORE_EVIDENCE_REQUIRED. Every result remains NO_ACTION because conditional scenarios are not approved trade plans and execution admission is unverified. An optimistic model cannot waive that. Completed reviews remove only the review-not-run diagnostic from the decision summary; original package gaps remain auditable. Expired reviews are explicitly historical. No live orders exist.

This milestone does not complete actionable trade calls: account-specific broker eligibility, executable prices/costs, catalyst verification and final admission still need connection. Generic conditional EUR scenarios are now supplied to all eight stages; their capital and fee assumptions are explicitly fictional. The old NVDA plan rehearsal is not silently reused for other symbols.

The current momentum shortlist requires 20 completed five-minute bars. Stock context is collected earlier, but this job does not yet run paid premarket/context reviews or their separate dashboard contract. Do not promise a stock decision at the opening tick. Coverage is the collector's requested universe, not every listed stock.

## Verification

807 local tests passed before deployment, including the new weekday/DST/scope gates, durable quota, lost-write behavior, budget headroom, archive validation and one-complete-cycle/no-second-model-call integration test. Live model completion and dashboard delivery must be verified from the subsequent production run, not inferred from these tests.

## V2 conditional scenario contract

`candidate-review-archive-v2` keeps the v1 envelope and result fields (both top-level `plan` values remain null; trade_authorized remains false), but carries `candidate-evidence-package-v2`. Its package `plan` is null or `conditional-eur-paper-scenario-v1`: symbol, currency EUR, native_currency, positive decimal-string entry_eur/stop_eur/target_eur/quantity/planned_loss_eur, assumed_round_trip_cost_eur, paper_capital_eur='500', assumed_round_trip_cost_bps='40', entry_buffer_bps='10', fx_rate, fx_source, aware expires_at/exit_by, trade_authorized=false, and bounded assumptions/trigger/invalidation/loss_note text. Require stop < entry < target; risk <= 20; package expiry <= plan expiry; same-day Dublin exit <=22:00; exact symbol/currency binding. The plan is conditional illustrative research with fictional capital and cost assumptions, never an approved trade. Every role now receives it. Missing broker/account/execution/catalyst checks still prevent admission. UI must show these assumptions alongside levels and must never enable actionable status.

Calendar enrichment already uses optional package calendar_source_ids and source keys `calendar:<sha256>`. Treat those as cited dated research, never independently confirmed catalysts. Preserve strict validation of unknown keys, source IDs, eight stages, original timestamps and hashes. Existing v1 archives must remain readable. No snapshot contract change, keys in browser, order controls or frontend-triggered AI calls.

The v2 fixture is synthetic test input only, not a paid/live result. Local validation expanded to 811 passing tests. Production model and ingestion checks remain required.
