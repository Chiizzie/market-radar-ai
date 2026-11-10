# Scanner evidence review — 2026-11-10

50 setups across 37 symbols. Historical evidence analysis only; no strategy change.

Source report as of 2026-11-10T23:33:21.860802+00:00; source protocol `abfaa5c8b4fd3e76a46dddd142bd4747765b32c0caf2c6122afe9dbff6c7e4e8`. Input hashes and complete hypothetical closed-trade rows are retained in the accompanying JSON.

| Arm | Closed | Wins / losses | Before flat costs | Flat costs | Net |
|---|---:|---:|---:|---:|---:|
| code_only | 11 | 2 / 9 | €0.96 | €21.91 | €-20.95 |
| ai_reviewed | 1 | 0 / 1 | €-2.67 | €1.99 | €-4.66 |

Trading net excludes separate AI research costs: €0.63 recorded estimated cost, with 39 candidates lacking a complete reconciliation (including unreviewed candidates; this does not imply extra spending). This does not establish the complete AI cost or the AI's comparative value.

## Entry and exit evidence

- code_only: entry_already_invalidated: 10, no_observed_eligible_fill: 25, scheduled_exit: 7, stop: 4, trigger_gap_exceeds_protocol_limit: 4
- ai_reviewed: no_action: 7, no_observed_eligible_fill: 1, not_reviewed: 39, review_incomplete: 2, scheduled_exit: 1

## Strategy and exposure context

| Strategy | Setups | Code closed | Code net | AI closed | AI net |
|---|---:|---:|---:|---:|---:|
| opening_continuation_30m_v1 | 3 | 0 | — | 0 | — |
| trend_continuation_20bar_v1 | 47 | 11 | €-20.95 | 1 | €-4.66 |

Repeated symbol setups: stocks:BRBR: 2, stocks:ENB: 5, stocks:FMC: 3, stocks:INVH: 3, stocks:MARA: 3, stocks:MGM: 2, stocks:TTEC: 2.

- code_only: peak 11 simultaneous hypothetical positions, €5501.73 assumed capital. These independent setups enforce no account capital limit.
- ai_reviewed: peak 1 simultaneous hypothetical positions, €500.05 assumed capital. These independent setups enforce no account capital limit.
- code_only: 11 observed fills; median wait 63.7s from enrolment/approval, median observed ask above trigger 0.85 bps. This is not broker execution latency.
- ai_reviewed: 1 observed fills; median wait 148.1s from enrolment/approval, median observed ask above trigger 0.93 bps. This is not broker execution latency.

## Capital and cost alternatives

| Profile | Arm | Considered | Closed | Net | Blocks |
|---|---|---:|---:|---:|---|
| eur_conversion | code_only | 50 | 0 | — | scenario_net_reward_below_2r: 50 |
| eur_conversion | ai_reviewed | 2 | 0 | — | scenario_net_reward_below_2r: 2 |
| usd_balance | code_only | 50 | 2 | €-1.95 | insufficient_shared_capital: 35, symbol_already_reserved: 4 |
| usd_balance | ai_reviewed | 2 | 1 | €-3.19 |  |
| stressed | code_only | 50 | 0 | — | scenario_net_reward_below_2r: 50 |
| stressed | ai_reviewed | 2 | 0 | — | scenario_net_reward_below_2r: 2 |

Alternative fictional EUR1000 portfolios; do not add them. This cumulative execution scope may span more than the selected evaluation day. Assumed USD/EUR routes, slippage and levies are not verified broker costs.

## One fixed exit diagnostic

At 15 minutes after the original observed fill, exit on the first fresh bid within 30 seconds only if sampled progress stayed below +0.5R. The chosen market observation must be at or after the evaluation time. Keep original stop/target, and refuse paths with any source-observation or receipt gap over 15 seconds, including the final source-to-receipt delay. This rule was proposed after seeing the day: it is hindsight-biased and is not activated.

- code_only: {'hypothetical_early_exit': 3, 'observation_gap': 7, 'progress_threshold_reached': 1}; paired cases 3 across 1 distinct symbols; paired delta €6.46.
- ai_reviewed: {'observation_gap': 1}; paired cases 0 across 0 distinct symbols; paired delta —.

The paired subset is selected by data coverage. Its delta is not a full-cohort or portfolio result; unavailable paths cannot be filled with assumed prices. Even dense sampled quotes cannot prove that no price crossed a threshold between observations.

## Next evaluation

Freeze the entry and cost protocol first. Collect later unseen sessions using the same candidates and entries; evaluate the one declared stall exit alongside the unchanged baseline. Preserve unknown paths, deduplicate symbol exposure in the capital book, reconcile broker costs, and report all arms rather than selecting a favourable result. A minimum sample checkpoint is a progress check, not statistical proof.

## Limits

- One day cannot establish profitability or AI value.
- Independent setups can duplicate symbols and assume more capital than the user has.
- Flat costs are assumptions; pre-cost P/L still embeds observed bid/ask spread.
- No-fill is not zero-profit execution and missing observations can hide triggers.
- No live or paper strategy rule, original decision, alert or outcome was changed.
