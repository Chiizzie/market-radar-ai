# Scanner quality audit — 23 November 2026

Evidence inspected in Europe/Dublin on 23 November, starting at 20:41. Deployment: main `9892f1a3494aed0e536fb84e78f9ebb3485c37f2`, including PRs #41–#43. This audit changes no runtime, trading rule, budget, alert, historical record or broker setting. Instrument prices remain USD; performance accounting is EUR.

## Assessment

The infrastructure is producing fresh captures and acknowledged watches again, but the system has not demonstrated positive net expectancy. The highest-value work is making a plan usable within the owner's 1–5 minute response range, admitting it under realistic costs, and completing observation/reconciliation. Adding more strategies or model roles is not supported by the evidence.

At the 20:48 inventory, 154 ordinary dispatches from 08:00 through 20:45 comprised 136 successes, 16 failures and two in progress: 89.5% of completed runs passed. Eight failures were the afternoon account-history incident; eight were comparison-watcher failures. A separate execution-report publication also failed. These are component failures, not 17 failures of market collection.

The 20:25, 20:30 and 20:35 scans each completed all 13 jobs successfully:
[20:25](https://github.com/Chiizzie/market-radar-ai/actions/runs/45259175522),
[20:30](https://github.com/Chiizzie/market-radar-ai/actions/runs/45260077746),
[20:35](https://github.com/Chiizzie/market-radar-ai/actions/runs/45260897379).

Independent database timestamp reads found the scanner capture generated 20:46:21.846 and stored 20:46:24.493, and the account snapshot generated 20:45:44.540 and stored 20:45:56.402. These reads prove storage, not the original HTTP acknowledgement. Separately, the original 20:30 capture receipt records generation 20:31:32.246 and acknowledgement 20:31:35.273 before its 20:32:32 expiry. A broader research-report database query returned HTTP 504; this audit therefore uses hash-verified original GitHub report ZIPs and names their actual cutoffs.

## Ranked work

| Priority | Finding and evidence | Concrete next change and acceptance check |
|---|---|---|
| 1 | Alerts do not fit a 3–5 minute manual response. Today's FPS, PTON and NVDA notifications were acknowledged at 20:23:35, 20:28:57 and 20:35:12. All three expired before the three- and five-minute response points. The cumulative USD manual scenarios likewise have 54/54 watches blocked by the response window at both delays. | Continue the existing frozen fresh-breakout/reconfirmation comparison. Measure valid, cost-qualified, observed entries at 1/3/5 minutes from acknowledgement. Do not merely extend expired plans or promote the new arm without later outcomes. |
| 2 | Live plan construction and execution-cost evaluation disagree. The latest manual EUR-conversion scenario blocks all 54 notified plans for net reward below 2R. Broker currency route/costs remain unverified. | Obtain a redacted matched entry/exit example and actual currency route from the owner. Run a separately versioned cost-aware preflight before paid review; retain the original baseline. Acceptance: costs reconcile and fewer unusable reviews without weakening risk/reward. |
| 3 | Knowledge preparation loses usable inputs during startup. A verified capture contains 30 original packets. Replaying the exact deployed knowledge runtime at 20:31:28.793 produces 30 pairs; at its real 20:32:07.885 start it produces zero and all 80 stock quotes are stale. | Preserve/hash-bind the collector's original packets for offline paired-input preparation. Record original evidence time separately from processing time. A later live decision must still refresh and pass its own freshness checks. Add fresh/stale/tampered/late-source fixtures. Do not backdate an AI decision. |
| 4 | Available coverage, rather than catalogue size, is limiting research. At 20:31, 5,723 stocks were in the candidate pool, 1,200 technically checked, 320 usable, 880 unavailable and 4,523 deferred. Only 80 received detailed research. The existing shadow diagnostic identifies 138 gapped histories with a contiguous latest 20-bar window. | Benchmark those existing recovery candidates against unchanged selection on original first-seen captures. Preserve symbol/feed/time checks and quantify extra valid setups, gaps and outcomes. The 138 are recoverable windows, not demonstrated profitable trades. |
| 5 | Unresolved historical exposure stalls shared-capital evaluation. Each USD execution arm reserves about €499 against a missing historical exit, leaving €496.35/€496.30 available. Fixed sizing produces 1,987 code and 50 AI cash blocks. | Reconcile only against genuine deadline evidence. Keep missing exits unresolved. Continue the already-replayed affordable-sizing alternative as a separate prospective protocol, with original risk/cost limits and existing reservations. Never reset the old portfolios to improve results. |
| 6 | Reliability and reporting remain incomplete. At 20:10 the watcher recorded 51 `market_clock_future` failures plus one unavailable quote; at 20:24 execution publication exhausted three HTTP 503 responses. | Retain request/response/local/provider timestamps to measure clock offset before considering any policy change. Separate report reconstruction from publication receipts; verify a hash-matched read after ambiguous writes. Count missed observations honestly. |
| 7 | Historical intelligence is behind the live scanner. The latest completed performance job at inspection began 19:20:44; its execution cutoff is 19:09:55 and manual cutoff 19:11:05. Intake still lists 75 pending artifacts and 76 capture runs absent from its index, some pending rather than genuinely lost. | Make completion-triggered, bounded intake resilient to delayed hourly scheduling. Show source cutoff and backlog on the dashboard. Preserve at-risk originals once with hash checks. Acceptance: backlog falls and absent/pending/expired states remain distinct. |
| 8 | Eight model calls do not yet establish additional trading value. The NVDA review used 86,394 input tokens, 1,406 output tokens and €0.065214 recorded model cost. Its six specialists already ran in parallel. Only five descriptive closed code/AI policy pairs were comparable in the performance report. | Test bounded, role-specific evidence and the already-designed simpler chief comparison within current caps. Compare refusals, valid entries, timing, cost and later net outcomes. Do not infer benefit from more approvals or from a smaller losing sample. |

The NVDA notification followed the original collection qualification by 223.34 seconds. At acknowledgement, 171.95 seconds remained before the original plan expiry. This is end-to-end observed delay; not all of it is model inference. Fresh requalification occurred during review, so the original collection and final packet must not be conflated.

## What is built but not yet proven

- **Opening paths:** the 15-minute opening-range and 30-minute continuation work exists. Today's earlier incident evidence records TSLA at 14:46 and HDB at 14:51 with no observed eligible fill inside their original one-minute windows. The first main guarded equity cohorts were at 16:12. The 19:09 cumulative sample is dominated by 1,912 trend-continuation cohorts out of 1,937; earlier action is not solved merely by having an opening experiment.
- **Knowledge:** a frozen 712-case bank and paired chief interface exist. The paid paired comparison is not scheduled; the preparation job makes zero model calls. More downloaded knowledge will not fix its demonstrated input-age bottleneck.
- **Volume/ATR/cost variants:** already deployed despite draft PR #18. Today's 271 cohorts have zero matched closes in six comparisons. The structural volume comparison has 11 matched closes with zero net difference. No winner is established.
- **Entry confirmation:** today's ask-trigger arm has 12 closes, all losses (−€39.52); the bid-confirmed arm has four, all losses (−€15.35). Only two pairs meet the coverage condition, with bid minus ask −€0.35. Different participation is not proof of better expectancy.
- **Fresh breakout:** at the older performance cutoff, validation has 14 notified watches, no closes, and one five-minute reconfirmation that remains blocked. Seven watches per response arm have unknown quote coverage.
- **Old draft PR #2:** pre-open preparation has a dashboard compatibility prerequisite and an old runtime base. It should be reconciled with today's implemented opening path, not merged wholesale.
- **Reporting inconsistency:** `execution_research.replay` counts unreviewed cohorts among `ai_cost_incomplete_cohorts`. Its 1,949 count is not 1,949 lost paid calls. The detailed performance report already separates attempted, unattempted and unsettled costs. Reuse that classification.

## Performance evidence and limits

These are **separate independent reference-price simulations**, not additive portfolio returns or the owner's account P/L. Cutoff: 19:09:55 Dublin, source since 12 November; assumed original costs and separately recorded AI expense.

| Arm | Closed | Wins / losses | Net EUR | Expectancy / close | Profit factor | Unresolved |
|---|---:|---:|---:|---:|---:|---:|
| Code-qualified independent setups | 136 | 24 / 112 | −371.61 | −2.73 | 0.231 | 98 |
| AI-reviewed independent setups | 9 | 3 / 6 | −34.84 | −3.87 | 0.178 | 8 |

The 20:18 execution export separately retains one USD code close (−€4.38) and three USD AI closes (−€4.42), with one unresolved exposure in each account. The 20:28:56 manual export separately retains one USD/60-second close (−€3.06) and an unresolved exposure. The primary EUR/300-second account has no closes; its balance is not evidence of break-even trading. Alternative books must never be added together.

The performance report has 106 unresolved independent outcomes, two unresolved shared-book reservations, two unsettled review costs and four missing alert clocks. These overlap and are not real broker-position counts. Its prospective gate remains blocked: insufficient closed sample and independent sessions, unverified costs, incomplete end-to-end evidence and no supported positive net expectancy. Today's session is still incomplete at these cutoffs.

## Verification and provenance

Ten original ZIPs were SHA-256 matched to GitHub artifact digests. The manifest beside this note records their IDs and names; raw captures and source journals were not published in this PR. The account inspection retrieved timestamps only.

The exact deployed knowledge revision `9ae20ef8454a654fabee488cba9c1fbed9ba664c` reproduced the 30-versus-zero result offline using unchanged capture/news/library bytes. This clock-sensitivity replay is diagnostic, not a retrospective live review. The standard report-assessment helper checked the original execution/readiness artifact formats and bindings; it correctly marked their age. It does not authenticate or independently replay source events.

No new paid model/provider calls, test Telegram messages, orders, alert replays, spending changes or historical rewrites were performed. No runtime was changed in this audit.

Sources:
- [Current deployment](https://github.com/Chiizzie/market-radar-ai/tree/9892f1a3494aed0e536fb84e78f9ebb3485c37f2)
- [Original performance job and saved source cutoffs](https://github.com/Chiizzie/market-radar-ai/actions/runs/45247958233)
- [20:10 quote/clock failure](https://github.com/Chiizzie/market-radar-ai/actions/runs/45256559711/job/137979814079)
- [Report reconstructed but publication failed](https://github.com/Chiizzie/market-radar-ai/actions/runs/45257898121/job/137984447281)
- [Manual export](https://github.com/Chiizzie/market-radar-ai/actions/runs/45259740913)
- [20:30 capture, decision, knowledge and experimental artifacts](https://github.com/Chiizzie/market-radar-ai/actions/runs/45260077746)
- [Earlier opening and cash-sizing replay](../incidents/2026-11-23-comparison-and-review-quality.md)
