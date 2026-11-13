# External research bank — 13 November 2026

Status: **implemented and tested offline**. This expands the scanner's research material; it does not activate new production signals, install external agents or replace the running scanner.

## What was added

- **12 curated notes** covering opening-range definitions, volatility context, mean-reversion failure modes and horizons, session calendars, information availability, chronological validation, label purging, future-data tests, signal/fill timing, costs and dependent trials.
- **Eight source records**, with exact GitHub commit, selected file blob IDs, license metadata, review date, scope and caveats. Seven sources contribute reference material; TradingAgents is deferred.
- Deterministic retrieval by strategy and optional topic, capped at **three notes / 4,500 UTF-8 bytes**. A note is methodological evidence, never a past trade, current catalyst or calibrated prediction.
- A separate offline comparison packet: existing playbook/case knowledge versus the identical packet plus relevant research notes. Both arms share the same current inputs, plan and instruction. The original two-arm experiment is unchanged.
- Two original local validation utilities: chronological event-label splitting with receipt-time checks, and future-data dependence checks. No external repository code was copied or executed.

The bank is `knowledge/external-research-20261113.json`. Approved content ID: `6ae9a6f1f03ffc4ad616be3115145039ff3a93cbfc42249c971c44b40c246e47`; built at **22:47:47.442910 Europe/Dublin**, after source review. Comparison protocol: `61d6d454a74def5c43144f0000430f0fbae6d32e62b463f117f2f909a10a1fcc`.

A changed bank must receive a new deliberately approved code binding. Recomputing its content hash alone cannot make modified material trusted. Missing topics return an empty result. The retrieval path rejects unknown strategies, future availability, duplicate IDs, undeclared fields and unresolved or deferred source references.

## Sources and review scope

| Project | Fixed revision | Declared license | Decision |
| --- | --- | --- | --- |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean/tree/82d26047e95a89b53c9cbe02b67efaa3c4455ed9) | `82d26047e95a` | Apache-2.0 | Selected material catalogued as reference |
| [skfolio/skfolio](https://github.com/skfolio/skfolio/tree/c32310558b41c0198c73c4f67f236e400f4fb959) | `c32310558b41` | BSD-3-Clause | Selected material catalogued as reference |
| [rsheftel/pandas_market_calendars](https://github.com/rsheftel/pandas_market_calendars/tree/f511a67c0826065a1e880e4e32dd4f86be6840e7) | `f511a67c0826` | MIT | Selected material catalogued as reference |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade/tree/5197bedab82559fac6be6c1539c64b94368fb91c) | `5197bedab825` | GPL-3.0 | Selected material catalogued as reference |
| [agiprolabs/claude-trading-skills](https://github.com/agiprolabs/claude-trading-skills/tree/981e1d736cdc02bdc1c55c74ec9224e956414706) | `981e1d736cdc` | MIT | Selected material catalogued as reference |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents/tree/9fa1196fffbcfd9de5146d2dd2869df84ab99838) | `9fa1196fffbc` | Apache-2.0 | Deferred; architecture reference only |
| [quantskills/skill-quant-research](https://github.com/quantskills/skill-quant-research/tree/457cc945d3f9ec587bae637c05e3b9c1e59b5428) | `457cc945d3f9` | GPL-3.0 | Selected material catalogued as reference |
| [alpacahq/alpaca-skills](https://github.com/alpacahq/alpaca-skills/tree/0e7c35163ae462730de1f4a0bfafceac82b7d59b) | `0e7c35163ae4` | Apache-2.0 | Selected material catalogued as reference |

These are **selected-document/code-section reviews**, not repository-wide security audits. The manifest lists exactly which files were fetched and records the review limitations. It is not permission to run the projects' installers, authentication flows, broker adapters or bundled commands. No new dependency, credential access, subscription or paid model operation was introduced.

Useful findings:

- LEAN's selected opening-breakout example has a five-minute description but a three-minute constant. The bank records this discrepancy instead of silently importing a presumed five-minute rule.
- Alpaca's official backtesting instructions emphasize reproducible source/assumption records. Its CLI workflow and bar-fill examples were not substituted for the scanner's existing quote-aware simulation.
- Skfolio supplies useful chronological-validation concepts. Its portfolio interfaces are not a direct replacement for scanner events, delayed result receipts or overlapping same-stock alternatives.
- Freqtrade's documented sliced-result comparisons motivate a targeted leakage test. The crypto engine and GPL implementation were not imported.
- The community collection offers hypotheses, but its mean-reversion diagnostics are not probabilities of profit. Its illustrative deflated-Sharpe description mixes annualized-SR language and inconsistent kurtosis labels. Those formulas, thresholds and sizing suggestions were not adopted.
- Packaged market calendars can support offline fixtures; they cannot establish a current halt or replace the scanner's observed session evidence.
- Quant Research's data and validation discipline is useful reference material. Its CSV script is not a complete intraday point-in-time data validator.
- TradingAgents overlaps the scanner's existing analytical roles and adds a substantial model/provider framework. A replacement needs a separate cost and same-input comparison; it is not installed here.

## How the new code is used

`agents/external_research.py` validates and retrieves curated notes, and prepares a new offline comparison from a valid existing strategy pair. It verifies the base pair again, freezes current evidence, checks note availability at the candidate's original assembly time, and rejects tampered or expired comparison packets. Research remains structurally separate from the historical-case list.

`agents/research_validation.py` supplies:

1. **Chronological folds:** earlier observed session dates train; later dates test. Strategy/source-policy partitions remain separate. Label overlap and results received too late remove training rows. Same-session groups cannot cross date boundaries. The optional gap is measured in observed dates, not an inferred exchange calendar.
2. **Future-data dependence audit:** a local extractor must produce the same historical snapshot with full input and with only the records available at the cutoff. A deliberately leaky whole-sample mean fails; an availability-filtered mean passes. Mutating inputs, errors, non-finite outputs and unexercised cutoffs do not become successful checks.

Neither utility fits a model, estimates a profitable strategy or promotes a signal. The prefix check only covers exercised cutoffs and paths. A split configuration is not a minimum sample size that proves an edge.

The comparison is **prepared only**: no new paid runner, reviewer citation validator or scheduled external-note injection is activated. Actual AI evaluation, citation handling and forward outcomes belong to a separately tested future runtime. The six-strategy worker already deployed remains pinned to `12e7b42144b693f6ecdb86aac36b04c57c5bb694`.

## What the existing case audit shows

The original **717 setups remain unchanged**, spanning **12 and 13 November only**. They contain **55 closed code simulations, 631 unfilled setups and 31 unresolved outcomes**. The closed simulations all belong to the guarded trend-continuation partition.

The auditor returns `insufficient_independent_history` for the configured chronological comparison. It preserves unfilled/unresolved counts and does not invent zero returns. Exact exit times are not present in the compact library, so its known-at clock conservatively bounds each closed label. Original journals are required for a tighter horizon. Repeated stock/session groups are described as clusters, not independent bets.

External reading expands methodological knowledge; it does not create more observed trades or more independent market sessions. Next evidence should come from later sessions under the frozen protocols, then a declared, budgeted comparison on the same setups.

## Reproduction and evidence

Run from the external-research source branch/revision recorded in the verification receipt:

```sh
python -m pip install -e '.[dev,market]'
python -m pytest -q
python scripts/verify_external_research.py --output artifacts/external-research/offline-receipt.json
```

The offline receipt exercises note retrieval for all seven strategy families and prepares/validates six comparison packets. Mean reversion stays offline. The source fixture inputs are synthetic; **zero model calls and EUR0 additional AI cost** are recorded.

[Offline receipt](evidence/external-research-offline-20261113.json) includes the unchanged library ID, source-bank ID, per-strategy note selection/size, controlled leakage demonstration and actual case-history audit. Final hosted verification and source revision are recorded in the companion verification receipt. Existing production workflow pins, budgets and trade admission remain unchanged.

Source revision: [`81a1dc65c29837158ba35ea9ae2e85b7a568f005`](https://github.com/Chiizzie/market-radar-ai/tree/81a1dc65c29837158ba35ea9ae2e85b7a568f005). [Curated source bank](https://github.com/Chiizzie/market-radar-ai/blob/81a1dc65c29837158ba35ea9ae2e85b7a568f005/knowledge/external-research-20261113.json). Local verification: **1,684 passed**, compilation and the complete offline integration receipt passed. Hosted verification: [43522684658](https://github.com/Chiizzie/market-radar-ai/actions/runs/43522684658). [Verification receipt](evidence/external-research-verification-20261113.json).
