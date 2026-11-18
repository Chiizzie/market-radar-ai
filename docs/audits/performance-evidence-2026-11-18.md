# Performance and reliability evidence audit — 18 November 2026

Evidence cutoff: 15:03 Europe/Dublin. This is a bounded audit of the current deployment and available immutable paper evidence, not a profitability certification or the user's actual brokerage P/L.

## Findings

1. **Main was not a reproducible source tree.** [PR #19's original CI run](https://github.com/Chiizzie/market-radar-ai/actions/runs/44327292535) failed with 16 collection/import errors. Production works from separate pinned source revisions. Main omitted deployed modules, tests and fixtures, and contained older shared modules. This PR restores exact published blobs with provenance. All live workflow files and runtime pins remain byte-for-byte unchanged.
2. **Current service recovered; hosting cause unresolved.** [The 14:45 scanner run](https://github.com/Chiizzie/market-radar-ai/actions/runs/44327741925) completed all 13 jobs. Scanner snapshot generated 14:50:57 / received 14:51:00; private account snapshot generated 14:50:37 / received 14:50:46. Only receipt metadata was used. The 14:50 and 14:55 scanner runs also succeeded. These snapshots do not prove continuous coverage or permanent resolution of the 17 November storage incident.
3. **Checkpoint recovery has live confirmation.** [Entry observer job 134883495042](https://github.com/Chiizzie/market-radar-ai/actions/runs/44327741925/job/134883495042) checked out `354a615`, restored the 14:40 enrolment cache, and published after 66 polls with zero error polls and no paid model calls. It had zero cohorts at this early-session snapshot; this does not establish peak-load coverage.
4. **The daily report hides cumulative history.** [Execution run 44327854314](https://github.com/Chiizzie/market-radar-ai/actions/runs/44327854314), as of 14:49:16, exported 127,984 events and 1,101 setups from 12 November onward. Its daily trade-evaluation report showed zero setups for 18 November. Full-history reporting must use source exports, not the public book's last 20 detail rows.
5. **Positive expectancy is not demonstrated.** Observed cost/shared-capital alternatives have very few closed trades, negative results, unverified broker costs and unresolved exposure. Alternative experiments cannot be pooled into an apparently larger sample or portfolio profit.
6. **Manual actionability is constrained.** [Manual run 44330110361](https://github.com/Chiizzie/market-radar-ai/actions/runs/44330110361) has 27 acknowledged alert clocks, all matched to reviews. EUR-conversion alternatives reject all 27 after costs. At 180/300 seconds, USD alternatives reject all 27 because the original entry window elapsed. The USD 60-second alternative has one closed trade, net −€3.057574, and one unresolved position retaining about €499. The declared primary remains `eur_conversion:300`; do not select a better-looking alternative retrospectively.

## Verified cumulative execution evidence

Source protocol: `eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8`.
Execution protocol: `010dac634261525d61b6e4acf6a822bbae80f3adb0b2565b361b038b39ab1618`.
Source SHA-256: `f239796e6935a3c2f3e3794e156e0bbfb4cb6594de7a1f2cbfad501a3ce49762`.

| Alternative book | Considered | Closed | Closed net EUR | Unresolved | Main limitation |
|---|---:|---:|---:|---:|---|
| EUR conversion / code | 1,101 | 0 | Unknown: no closed trades | 0 | 1,096 below net 2R; five unsupported markets |
| EUR conversion / AI | 51 | 0 | Unknown: no closed trades | 0 | 48 below net 2R; three unsupported markets |
| USD balance / code | 1,101 | 1 | −4.376654 | 1 | 1,048 blocked for shared capital |
| USD balance / AI | 51 | 3 | −4.422799 | 1 | 24 blocked for shared capital |
| Stressed conversion / code or AI | 1,101 / 51 | 0 / 0 | Unknown: no closed trades | 0 / 0 | Cost gate |

These are six alternative fictional €1,000 portfolios. Buy-ask/sell-bid already includes the reference spread. Slippage, FX and levies are assumptions, not confirmed broker charges. Recorded AI cost of €3.456410 is separate from these trading totals. The existing report flags 1,029 cohorts without complete AI costs, including unreviewed cohorts; new reporting must distinguish unattempted reviews from attempted reviews with missing settlements. An unresolved position is not a zero-profit exit and cannot silently release capital.

## Existing controlled experiments

Latest durable 17 November reports stopped before the outage ended; they are incomplete session observations:

- Volume/risk/cost protocol `c796287f…`: 154 cohorts at 20:09:06, ten frozen variants. Closed counts range 0–9. All variants with closed trades have negative closed totals; some retain open/unresolved positions. Same-time structural USD: one win, eight losses, net −€26.047124. This is not a shared portfolio or a valid basis to select a winner.
- Entry confirmation `c73bb1ce…`: 160 cohorts at 20:23:16. Ask-trigger: four closed, −€5.211874. Bid-confirmed: three closed, −€0.940772. **Zero adequately covered pairs**; three both-closed pairs are coverage-selected. No valid improvement claim follows from the difference.
- Manual alert audit `b36797c1…`: 15 clocks on 17 November, plus three approved reviews without a clock in that audit. Missing acknowledgement does not prove delivery or non-delivery; do not resend historical alerts.
- Historical storage reads in the cumulative execution job took roughly 125 seconds over seven dates. Disk replay removed a former memory ceiling, but full-history reads still add load. New analytics should reuse exports, without another database reader.

Evidence: execution artifact `14438666429`, manual portfolio artifact `14437769991`, and bounded read-only queries of the public paper-research journal. Private brokerage fills are excluded.

## Reliability history and remaining blockers

- The final 100 runs returned for 17 November include scanner failures from 21:00 through 22:55. This bounded query is not a full-day success-rate estimate. The incident distinguishes observer restore deadlines from later shared-storage timeouts; provider root cause remains unproven.
- Some execution runs are cancelled, including 18 November 14:52. Concurrency supersession is a possible explanation, not a verified scanner crash or confirmed root cause.
- The execution source excludes candidates rejected before paper enrolment. Alert acknowledgements are incomplete before clock instrumentation. Missing history must remain explicit.
- IEX reference observations are not Trading 212 fills. Unverified costs/currency route, quote gaps, unresolved exits and missing receipts block a profitability claim.
- Later out-of-sample sessions cannot be manufactured. Freeze the baseline, show all alternatives, and separate implementation completion from prospective validation.

## Engineering result and continuation

The combined restored source passes **1,936 tests and 22 subtests** locally. The restoration manifest binds each changed/restored file to an existing Git blob and originating runtime commit. No historical trade record, live workflow, source protocol, spending limit, alert or broker-execution switch changes.

Continue with full-history EUR metrics and indexed lifecycle projections from existing exports; reconciliation exceptions; common-cohort comparisons; causal market-context joins; and a predeclared prospective gate. Recover rejected candidates from retained capture artifacts while disclosing unavailable earlier captures. No automatic promotion to brokerage execution.
