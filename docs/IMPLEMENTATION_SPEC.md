# Market Radar AI — Implementation Specification v1.0

## Approved decisions
- Strong model tier for all six specialist agents.
- Broad discovery across eligible equities and liquid crypto.
- Qualified Telegram alerts.
- Independent first-pass analysis, then structured debate.
- Both annotated charts and written levels.
- Separate project; existing Market Radar is read-only as an optional candidate source.
- Paper trading only.

## Components
1. Ingestion: market data, news, corporate events, candidate feed and broker instrument metadata.
2. Validation: timestamps, source provenance, symbol mapping, currency conversion, stale-data checks and completeness checks.
3. Candidate store: immutable snapshots and deduplication.
4. Agent runtime: six independent agent contracts with versioned prompts/model metadata.
5. Debate engine: evidence-led challenges after first-pass reports are frozen.
6. Decision engine: final classification plus hard risk/data gates.
7. Technical output: annotated chart and machine-readable written levels from the same snapshot.
8. Paper portfolio: simulated fills, fees, spread assumptions, stops, targets and outcome tracking.
9. Alerts: qualified Telegram messages with idempotency keys.
10. Evaluation: agent calibration, false positives, missed opportunities and strategy-level paper results.

## Agent contracts
Every agent returns: candidate_id, agent_id, model_id, prompt_version, generated_at, data_snapshot_id, direction, verdict, confidence, evidence[], risks[], missing_data[], and rationale.

The technical agent additionally returns timeframe analyses, support/resistance, VWAP, trendlines, entry trigger, stop, targets, invalidation and chart artifact references.

The risk agent returns max_loss_eur, proposed_quantity, estimated_fees, spread_assumption, liquidity assessment, broker eligibility, holding-period constraints and hard_gate_results.

The final agent returns ACTIONABLE_NOW, WATCH_FOR_ENTRY or NO_ACTION, a concise rationale, unresolved objections, and a trade plan only when every hard gate passes.

## Mandatory gates
- Paper-only execution mode.
- Planned loss <= EUR 20.
- Data freshness and source completeness pass.
- Entry, stop and targets are grounded in the same snapshot.
- Positive, acceptable risk/reward under configured policy.
- Instrument and direction supported by a verified broker catalogue.
- Intraday trades cannot carry past 22:00 Europe/Dublin.
- Any failed mandatory gate forces NO_ACTION.

## Phased delivery
Phase 1: foundation, schemas, storage, validation and tests.
Phase 2: provider adapters and candidate ingestion.
Phase 3: specialist agents and independent report persistence.
Phase 4: debate and final decision.
Phase 5: chart rendering and alert qualification.
Phase 6: paper trading and outcome tracking.
Phase 7: evaluation against the existing scanner; integration considered only with explicit approval.

## Security and isolation
No production credentials from the existing scanner are copied. No writes are made to its repository, workflows, secrets or deployment. Any future candidate feed is read-only and schema-validated.
