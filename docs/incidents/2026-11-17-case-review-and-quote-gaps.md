# Trade-case intake and quote failures — 17 November 2026

## Verified operating state

The shared data path was functioning during this inspection. The 18:15 private sync delivered at 18:15:45; a current private account receipt was observed at 18:25:42.506434 without publishing its contents. Current research rows were read successfully. The [18:20 main scan](https://github.com/Chiizzie/market-radar-ai/actions/runs/44146730682) completed all 13 jobs successfully. This establishes recovery at these checks, not the cause or exact time of recovery from the 16 November incident. No restart completion or support intervention was inferred. The previously prepared support draft remains unsent.

## Failure emails

| Dispatch | Run / failed job | Evidence |
| --- | --- | --- |
| 16:15 | [44123643073 / 134181406658](https://github.com/Chiizzie/market-radar-ai/actions/runs/44123643073/job/134181406658) | Twenty-five stale OPRA observations; an 84.973942-second recovered gap and a later unresolved gap. Other 12 jobs passed. |
| 17:45 | [44140433531 / 134241443450](https://github.com/Chiizzie/market-radar-ai/actions/runs/44140433531/job/134241443450) | Two stale OCTV quotes; its gap remained unresolved when the watcher stopped. Other 12 jobs passed. |
| 18:10 | [44144929915 / 134257362530](https://github.com/Chiizzie/market-radar-ai/actions/runs/44144929915/job/134257362530) | Sixteen stale GLBE observations. A recovered gap lasted 35.066811 seconds and another remained unresolved. Other 12 jobs passed. |
| 18:15 | [44145839649 / 134260600804](https://github.com/Chiizzie/market-radar-ai/actions/runs/44145839649/job/134260600804) | Five quote failures: BNL/NAVN staleness recovered within 10.060883 seconds; PTON and CSX were rejected as future_quote. Other 12 jobs passed. |

The comparison watchers received 90, 625, 785 and 701 valid quotes respectively and then reported `completed_with_gaps` / `critical_failure=true`. This was degraded comparison evidence, not four application-process crashes or another demonstrated database outage. The Node deprecation lines were warnings, not the failing steps.

Current comparison source remains `208f4bf5f9f1f403fb977075f0ea33912f4463b0`. Its ReferenceObserver evaluates after quote receipt, so inspection does not establish a pre-request-clock programming defect. The exact future offset is not retained in these failure strings; provider versus runner timing remains unestablished. Do not relax the non-future/30-second quote checks or the 30-second recovered-gap allowance to remove failure emails. Next diagnostic improvement: retain sanitized provider quote time, receipt/evaluation time and signed age for rejected observations; keep acceptance policy unchanged.

The 18:21:53 readiness report separately recorded EUR0.146377 remaining daily allowance against EUR0.15 required headroom. That is a normal budget deferral, not these failures. No allowance was changed.

## Development case bank

Added [three setup cases](../../knowledge/development-cases-20261117.json) for HUN, CSGP and VFC, from original saved measurement packets and numeric plans. Actual account fills and P/L are excluded from this public repository. All three share the same chart-led continuation strategy. A later HUN approval is kept distinct and is not counted as an independent success or substituted for the original call.

The case intake is offline development material; the frozen active knowledge library, validation protocol, decision prompts and workflow pins are unchanged. Three selected same-session examples do not establish an edge or an exit probability. The next comparison is original stop/target/session exits versus a predeclared two-completed-close failed-breakout exit, evaluated using later quotes and realistic costs, across all eligible setups and later unseen sessions.

Use authoritative plan arithmetic, not model narrative, for levels. In the first HUN review, the technical narrative quotes target 9.6487 while its actual plan and FX derive USD9.52916124. The saved plan is retained unchanged; numeric narrative reliability is a separate quality issue to test.

## Holding review semantics

At deployed account source `dbafe2c37e52ecd43fa85f404abd53d069f15995`, `position-monitor-v1` marks `failed_breakout` after two consecutive completed five-minute candles, entirely after the holding opened, close below the original trigger. It is not based simply on the user's fill price, and it can precede a stop breach. Stop/target/cutoff/data-unavailable reasons remain distinct. This monitor places no orders and uses periodic IEX observations, not broker stop protection. Never infer a historical alert's exact timestamp or candle prices from a later account snapshot.

## Verification and scope

Exact active workflow pins and source were inspected; all job conclusions and bounded failure logs above were checked. Private matched-fill quantities and cash arithmetic reconciled locally; saved plan/FX arithmetic matched original measured triggers. The evidence helper accepted the retrieved guarded execution/readiness protocol and retained budget, incomplete cost, pending coverage and unresolved-exit limitations. It did not independently replay/authenticate source history.

No new runtime code, paid model calls, messages, order operations, strategy thresholds, risk limits, budget changes or historical rewrites were introduced. This is a case-intake and operational evidence update, not a claim that quote-feed reliability or trading performance is proven.
