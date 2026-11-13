# 13 November 2026: entry-quality follow-up

Read-only follow-up after the user asked what else could be done now. No new model calls, orders, subscription, budget adjustment or strategy change.

## Current operations

The 19:00 scan [43488085070](https://github.com/Chiizzie/market-radar-ai/actions/runs/43488085070) completed with all eight jobs successful. Readiness event 193665 (report 19:10:40.605722 Dublin, receipt 19:11:21.545282) has eleven passes and the unchanged daily AI-headroom block. Execution event 193176 has the same evaluation day. The evidence helper validated both at 19:14:41.857576; live readiness remains unestablished.

## Replayed evidence

Strategy runtime: `fc12be18156a2ebbef2141275bf07f3962655e71`. Artifact `14067983384`, `strategy-experiment-43488085070`, downloaded SHA256 `06e7d90b47977d82ba556dce023a928b6eaf9919f759e2c357a05d0fa32c8ca9`. Report as-of 19:09:03.560217 Dublin. All 12,562 source events were replayed through the existing exact runtime; cohort identities and all variant totals reproduced. Canonical source-event SHA256 `9370445c6188db8f1f01d2a336ddc729fc1939291445501c663e4bf2e6eb0536` matched the archived report. This checks artifact and replay consistency, not broker fills or underlying provider accuracy.

Daily strategy-diagnostic event 192495 covers 182 common cohorts. In `rolling_atr_usd`, 171 fail the net reward >=2R gate; volume blockers overlap. In the separate `rolling_structural_usd` variant, states are 101 blocked, 65 unfilled, five closed, five open, four unresolved and two watching. All five closed outcomes are stops; do not treat the incomplete closed subset as the whole strategy or add alternative variants together.

| Symbol | Entry spread (bps) | Initial bid shortfall as % of actual fill-to-stop distance | Bid reached original trigger before exit? | Closed simulated P/L (EUR) |
| --- | ---: | ---: | --- | ---: |
| ZTO | 4.91 | 23.7% | No recorded observation | -2.47 |
| STNE | 12.68 | 14.8% | Yes | -6.21 |
| ARR | 16.86 | 39.3% | No recorded observation | -3.04 |
| CSX | 1.91 | 27.6% | No recorded observation | -1.66 |
| SNAP | 18.92 | 33.6% | No recorded observation | -4.30 |

All five entry bids were below the frozen breakout trigger, while asks had crossed it. Entry quotes were 0.20–3.43 seconds old at the durable simulated entry, so these five examples do not show stale entry data. Four had no subsequent recorded bid reach the trigger or simulated entry before their stop exits. Only sampled IEX quotes are known; this is not proof about intrapoll prices, full-market prices or broker execution.

The initial shortfall formula is `(simulated entry fill - observed entry bid) / (simulated entry fill - stop)`. It includes observed spread and the existing assumed five-basis-point entry slippage. It is not extra P/L to subtract again. The existing strategy already buys at ask and sells at bid. Numerical details: [entry-quality replay](evidence/2026-11-13-entry-quality-replay.json).

## Next measurable milestone

Hypothesis to test: an ask-only crossing can admit a weak breakout when the sellable reference bid remains below the trigger; requiring bid confirmation may improve entry quality but can also miss later winners or enter late.

Prepare a separate prospective paper comparison of the unchanged ask-trigger control against a bid-confirmed trigger, using the same candidate universe, fees, risk limits, quote-quality rules, entry expiry and exit policy. Freeze it before a later unseen session. Compare closed net outcomes, entry delay, spread/stop ratios, missed fills, open/unresolved cases and coverage. Do not delete current losers, optimize a cutoff on these five examples, or infer the alternative would have avoided their losses. This experiment has not been activated.

The separate new-prompt decision report (event 193316, as-of 19:11:04.003827) traces 265 cohorts but only four review cases enter the selection comparison; there are zero matched closed comparisons. VFC's actual AI simulation is open even though its frozen baseline selection counterfactual is unfilled. Keep those distinct; do not claim every actual reviewed trade is unfilled.
