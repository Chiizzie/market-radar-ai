# Market Radar AI: continue here

Last verified: 13 November 2026; the expanded strategy-routing worker succeeded in the 22:35 scan and reported at 22:36:27 Europe/Dublin. Its 717-case library and pre-validation guard are verified. Active-session coverage and performance remain unverified. Refresh source and production evidence before editing.

## Confirmed manual test profile: 13 November

Charlie supplied **EUR1,000 starting paper capital, EUR50 daily loss ceiling, all-day availability within existing trading hours and a 1–5 minute alert response**. No further user input is required for the next engineering step.

The [test specification](manual-execution-test-profile.md) and [profile JSON](../config/research/manual-execution-20261113.json) preserve EUR20 per-trade risk, the existing EUR40 combined open-risk limit, EUR500 allocation / three reservations, Invest scope, intraday rules and the Dublin 22:00 entry cutoff. Response scenarios are 60/180/300 seconds; 300 is the conservative benchmark, not an assumed probability distribution.

Source revision: [`512ebbfe9fd569b3e48ca5d5bf451c62fee7860f`](https://github.com/Chiizzie/market-radar-ai/commit/512ebbfe9fd569b3e48ca5d5bf451c62fee7860f), branch `research/manual-execution-profile-20261113`. The new module supplies additional **offline** profile/risk/timing gates and 41 passing synthetic boundary tests. It is not integrated into the scheduled scanner or a new fill engine. Existing runtime pins, frozen libraries and portfolio results are unchanged. See [offline receipt](evidence/manual-execution-profile-20261113.json).

The day limit includes net realised loss plus risk reserved for pending/open/unresolved positions. A future integration must persist the daily halt latch, supply dated reconciled state, and use actual alert-receipt evidence. Missing receipt/cost data stays unknown; an expired setup is never extended to accommodate the user's reaction time. The test profile alone does not enforce a live daily stop or establish profitability.

Next: integrate this profile into a separately frozen prospective replay, verify alert-receipt coverage, and reconcile actual Invest fee/FX data. These settings are complete; performance evidence is still pending.

## Knowledge-first research supplement: 13 November

The user requested more knowledge now, then the inputs needed to improve and build testing later. Added a content-only [primary-source supplement](../knowledge/primary-research-supplement-20261113.json): **12 additional notes / 12 official pages**, 24 notes across both research collections. It is not wired into runtime retrieval or scheduled AI. The existing bank, case libraries, source pins and budgets remain unchanged.

The [requirements brief](knowledge-and-testing-inputs-20261113.md) prioritizes retaining actual Invest fee/FX fields, modelling manual reaction time, verifying historical feed access, and preserving primary catalyst/halt timestamps. The deployed Invest importer already collects fill history; do not request a full CSV or new keys before using that access. Its parser drops `walletImpact.fxRate`, `walletImpact.taxes` and `order.initiatedFrom`. This is a documented future change, not implemented in this content-only turn.

Those three inputs have now been supplied; use the confirmed manual test profile above. Keep Invest as the initial scope; EUR20 planned per-trade loss, intraday and 22:00 entry cutoff remain. Historical SIP access on this account is unverified: Alpaca's historical FAQ and Paper Only entitlement guidance differ in scope, so a bounded access check should precede any purchase recommendation.

Read-only operational refresh: [43523131703](https://github.com/Chiizzie/market-radar-ai/actions/runs/43523131703) completed all 12 jobs after the regular session. Private account sync reported delivery at 22:55:38 Dublin. Latest SIP audit was `forbidden_unclassified`; do not label that specific response a confirmed subscription restriction. Its stale IEX observations were after close. This does not establish in-session performance.

[Content-review receipt](evidence/knowledge-inputs-review-20261113.json) records integrity checks. No expanded testing campaign or new paid calls, broker operations or dependencies were introduced. The prior 1,684-test result remains historical code evidence, not a newly run suite.

## External research bank: offline expansion, 13 November

The user asked to build the knowledge bank further using useful GitHub skills/code. A source-controlled offline expansion is implemented at `81a1dc65c29837158ba35ea9ae2e85b7a568f005` on `improve/external-research-20261113`: 12 authored research notes, eight fixed-revision source records (seven reference sources, TradingAgents deferred), bounded strategy/topic retrieval and a separate existing-knowledge versus expanded-knowledge comparison packet. This is an offline addition, not an installed third-party skill bundle or changed scheduled reviewer.

Original local code adds chronological event-label splits with source-policy partitions, outcome/receipt-time purging and observed-date gaps, plus a future-data dependence auditor. All 1,684 tests pass locally; offline integration covers seven strategy families and six prepared comparison packets. A deliberately leaky full-sample statistic is detected. Zero paid model calls, new external dependencies or broker operations occurred. Hosted CI: [43522684658](https://github.com/Chiizzie/market-radar-ai/actions/runs/43522684658).

The actual 717-case audit finds only two sessions (12–13 November), with 55 closed / 631 unfilled / 31 unresolved code outcomes. The configured chronological validation reports insufficient independent history. Do not present external notes as additional trades, treat correlated alerts as independent bets, or use the compact known-at horizon as a precise exit time. New comparison packets are prepared only: actual AI runner/citation validation and forward outcomes remain separate work. All current workflow pins and budgets are unchanged.

Bank ID `6ae9a6f1f03ffc4ad616be3115145039ff3a93cbfc42249c971c44b40c246e47`; built 22:47:47.442910 Dublin. See [external research record](external-research-bank-v1.md), [offline evidence](evidence/external-research-offline-20261113.json) and [verification receipt](evidence/external-research-verification-20261113.json). Review exact source licenses, code, permissions and assumptions before any later installation; this review covered selected material only.

## Expanded independent strategies: implemented 13 November

Runtime `12e7b42144b693f6ecdb86aac36b04c57c5bb694` on `improve/strategy-routing-20261113` adds a separate free `strategy-routing` research worker. Six strategies evaluate identical fresh stock inputs independently: 20-bar continuation, pullback reclaim, 30-minute opening continuation, 15-minute opening range, session-open anchored VWAP and competitor-strength breakout. Multiple applicable plans are retained as overlapping alternatives. The seventh family, intraday range mean reversion, is implemented and tested offline only; the scheduled worker and paired AI exclude it.

The new frozen library has **717 setups: 55 closed, 631 not filled and 31 unresolved**. All five additional method cases are unfilled; no added profitable-trade evidence exists. Original labels, receipt cutoffs, source protocol and quote/exit policies remain explicit. Cutoff `2026-11-13T21:17:12+00:00`, built `2026-11-13T22:19:07.593130+00:00`, library `b5b894a29e3cf2873e1e719ccf912a07ab525b46e1e3f93729c84d7bc134b6aa`. The original 712-case worker remains unchanged.

All **1,656 tests** pass locally. Offline fixtures exercise all seven real detectors and six with/without-knowledge pairs through a synthetic reviewer, with zero model calls and EUR0 AI cost. Exact replay of 223 original method events reproduces the new library. Final hosted checks: [43519887067](https://github.com/Chiizzie/market-radar-ai/actions/runs/43519887067). See [implementation and remaining validation](strategy-routing-v2.md), [offline receipt](evidence/strategy-routing-offline-20261113.json) and [deployment receipt](evidence/strategy-routing-deployment-20261113.json).

The new worker only prepares research inputs and artifacts. No production alerts, trade approvals, orders, paid AI comparisons, subscriptions or budget increases are activated. Prospective preparation starts **16 November 2026**. New alternative plans still need forward outcome observation and a budgeted actual knowledge/no-knowledge comparison before making performance claims. Preserve existing production pins and the v1 experiment; do not infer that this isolated worker replaces the original selector.

Deployment verified: [run 43520477027, job 132213533796](https://github.com/Chiizzie/market-radar-ai/actions/runs/43520477027/job/132213533796) succeeded at 22:36 Dublin. Exact runtime, installed library, zero calls and `outside_strategy_validation_or_session` were checked in the logs and downloaded artifact. Full scan still had observers running at that observation; do not call all jobs complete. Main deployment commit: `22b1dbe3165aa0eb7ade334c30bcee4d80a24f86`.

## Playbooks and past-case retrieval: implemented 13 November

The user approved the offline knowledge milestone and later-data comparison. Verified runtime: `9ae20ef8454a654fabee488cba9c1fbed9ba664c` on `improve/knowledge-retrieval-20261113`. The new `knowledge-shadow` worker only prepares inputs and makes zero model calls. Existing production collector/reviewer/observer pins, alerts, risk gates and budgets remain unchanged.

Frozen history cutoff: 13 November 21:17:12 Dublin; actual index build 21:41:28.972928. The library retains 712 stock cohorts: 55 closed code-only simulations (40 losses/15 wins), 626 unfilled and 31 unresolved. Only three AI-reviewed simulations closed. Do not treat 712 cases as 712 completed trades. There are no pullback/reclaim cases in this initial compatible population.

Three existing-strategy playbooks, deterministic matching (max three cases / 7,200 bytes), point-in-time receipt guards, independent paired chief inputs and a manual future metered comparison runner are implemented. The paired runner is not scheduled; it requires `--paid`, unchanged global budgets and a durable one-pair-per-day claim. No paid AI calls were made for this milestone. Fresh validation starts 16 November; future decision quality/profit improvement is unproven.

See [implementation, provenance and remaining validation](knowledge-retrieval-v1.md) and [offline receipt](evidence/knowledge-offline-20261113.json). Raw journals were independently replayed to the identical library hash. Source history export: [43512536368](https://github.com/Chiizzie/market-radar-ai/actions/runs/43512536368). Local expanded suite: 1,622 passed. Final hosted verification: [43514177316](https://github.com/Chiizzie/market-radar-ai/actions/runs/43514177316), 1,622 tests plus the committed-library offline check. A hosted test initially depended on an undeclared optional YAML package; the boundary test was corrected and the exact final source passed.

## Scope and current deployment

The user asked to finish the engineering milestones from the earlier chat: review reliability, missed-entry tracing, explanation of frozen strategy results, and six reviewers versus code-only and independent-chief evidence. They then authorized fixing the remaining ledger growth and quote-reliability issues. Keep ordinary scans running and use direct repository edits instead of paid Lovable editing-agent credits.

- Backend: https://github.com/Chiizzie/market-radar-ai
- Dashboard source: https://github.com/Chiizzie/pixel-perfect-replay-32614
- Dashboard: https://pixel-perfect-replay-32614.lovable.app
- Main workflow: `.github/workflows/scheduled-scanner.yml`; each job has an explicit runtime SHA. Main source is not the deployed runtime and still has pre-existing missing legacy modules.
- Collection, review and comparison runtime: `208f4bf5f9f1f403fb977075f0ea33912f4463b0`. Ledger maintenance remains `5ca5ffe1354729ddbbb735f8055fd0d50656f6d0`.
- Execution/readiness and operations reporting: `839af4f09abc6e7e21daa5bd41c56e587c96b25f`.
- Strategy runtime: `5002a0e004b89bb9c17895fa6d19d5ce3ed236e6`; entry runtime: `1f777dff0d7ae883cc54e6657a0ece8807c57d09`; method: `889f1a110f9f7ac9d88dbbbc7e9548e8fe00f2c5`; context: `7a518a9b8e8450612a3291e716814c811eba4e67`. Paper watcher/account sync remain `3a113a4e8c4e03e9b28799c146db1f1cae6f987a`.
- Dashboard contracts: `0210a0133233e0988fb6179c1d7d658d3d1701fb`.
- Latest runtime deployment: `52a2920c7ffdbc95afe05a60dc5db11e05619b74`. Supplemental quote-permission probe: `a913bb2efd7b2db55fb892bf2d9f22c6d1e8bb8c`.
- Earlier source CI: [43484084327](https://github.com/Chiizzie/market-radar-ai/actions/runs/43484084327), 1,580 tests plus offline fixtures. Main budget compatibility: 50 tests.
- Earlier budget deployment verification: [43485677181](https://github.com/Chiizzie/market-radar-ai/actions/runs/43485677181), all eight jobs passed, completed 18:53:11 Dublin.
- Detailed receipts and unresolved limits: [budget rotation and quote feeds](incidents/2026-11-13-budget-rotation-and-quote-feeds.md).
- Previous four-milestone work: [review and evidence milestones](incidents/2026-11-13-review-and-evidence-milestones.md).

- Latest reliability checks: [43507049241](https://github.com/Chiizzie/market-radar-ai/actions/runs/43507049241), all six runtime suites and production replay; final entry follow-up [43507384567](https://github.com/Chiizzie/market-radar-ai/actions/runs/43507384567), 1,591 tests.

## Verified fixes and limits

| Area | Verified state | Remaining evidence or dependency |
| --- | --- | --- |
| Review reliability | Atomic markers and incomplete-response accounting preserved; durable archives deployed and independently reconstructed | Sustained reliability; legacy main cleanup |
| Ledger growth | Active file reduced 402,298 to 120,590 bytes; all 1,069 records and six unresolved reservations retained in root plus three immutable archives | Rotation is bounded, not unlimited; never delete holds or reset allowances |
| Quote reliability | 63 polls / 1,257 quotes; maximum polling gap 5.49 seconds; BROS stale gap recovered; recurrent IEX/SIP diagnostics active | IEX can be stale or wide; SIP request refused with subscription-related HTTP403 |
| Missed-entry tracing | Latest decision evidence covers 208 cohorts and distinguishes review timing from missing/invalid quotes | A later rally is not proven recoverable profit |
| Strategy explanation | Blocker and target-cap diagnostics active for the frozen variants | Independent future-session performance and broker costs |
| Reviewer value | Existing code/chief/team calls compared without extra AI calls | Four new-prompt cases are unfilled, zero matched closed outcomes; no demonstrated added value |

The latest review job succeeded by returning `budget_deferred` with zero model calls. Current daily allowance remaining EUR0.129096 is below the unchanged EUR0.15 attempt requirement. Monthly remaining EUR3.710817 and lifetime EUR93.710817 do not override the daily cap. Routine scanning and observation continue. Do not call this a newly completed paid review.

The first natural scan had a recovered BROS stale-quote gap of 14.86 seconds and slow startup synchronization around 16.83 seconds. Its success is one completed-run observation, not proof of uninterrupted coverage. The independent follow-up probe confirmed HTTP403 with `subscription_restriction_reported: true`; broad SIP access is not enabled. Alpaca lists all-exchange Algo Trader Plus at USD99/month, checked against official docs on 13 November; no purchase or subscription change is authorized or made.

## Evidence and continuation

Lovable project `97051425-8afb-4ea6-bf3e-f6e5fc127ba3`: SELECT-only audit reads. Signed `research_events` retain forward reports and source events. Final review archives are in **`candidate_reviews`**; `paper_reviews` is older. Keep source/report/receipt timestamps separate and preserve full evidence internally while printing bounded summaries.

The cumulative execution portfolios since 12 November are separate from daily strategy variants. Alternative portfolios overlap; do not add their P/L or trade counts. Unfilled, open and unresolved outcomes are not zero-profit closed trades. The latest code/chief/team comparison has no matched closed cases despite older series having some closed simulated outcomes.

Next: decide how to address quote-feed access, then collect independent future-session evidence under frozen protocols. Any changed source must start a separate prospective experiment and retain the old outcomes. Do not weaken freshness/spread/risk gates or tune targets to make old results look better. Existing full diagnostic reports do not yet have their own dashboard panel.

Use Dublin timestamps, USD instrument prices and EUR allowances/risk. Preserve EUR20 planned risk, intraday limits and no entries at/after 22:00. Leave original `Chiizzie/market-radar` untouched. No live orders, paid data subscription, increased AI allowance, or hosting migration has been activated by this work.

## Latest follow-up: entry quality

A read-only replay at about 19:19 Dublin reproduced 12,562 source events and all strategy-variant totals. In the five closed `rolling_structural_usd` examples, entry asks crossed the trigger while bids remained below it; four had no later recorded bid reach the trigger before their stop exits. Existing spread plus assumed entry slippage initially consumed 15–39% of fill-to-stop distance. This is a small incomplete sample, not proof of a replacement rule. This finding motivated the separately frozen prospective comparison implemented below; production trade admission remains unchanged. See [entry-quality follow-up](incidents/2026-11-13-entry-quality-follow-up.md), including provenance and the distinction between actual AI positions and frozen selection counterfactuals.

## Entry-quality implementation (13 November, 19:59 Dublin)

The user authorized improving overall scanner quality. A separate paired entry-confirmation experiment is now wired into the normal workflow, pinned to `08809c9349d8c400b55625996ee1ee9649acfd44`. The original strategy stays pinned to fc12be1 and all other jobs are unchanged. Protocol `c73bb1ce0fe2f7e1db2cfa27d4fafdad8d65f31de1e12ff5514cc647d5dc27dc` reuses the same USD structural plans and costs; only bid >= trigger differs. It has an independent observer, durable restart, bounded concurrency and no model/notification/order operations. Commissioning is 13 Nov; validation sampling starts 16 Nov. Do not tune on commissioning outcomes.

Source CI [43496893665](https://github.com/Chiizzie/market-radar-ai/actions/runs/43496893665) passed all 1,580 tests and compilation. Replay of the original 12,562 recorded events reproduced all ten original variant totals unchanged. Dashboard: 726 offline tests plus 12 live access checks passed (the latter needed a network-timeout retry); typecheck and build pass. The private Performance page displays paired outcomes, entry cost components, incomplete states and experiment screen blockers. Detail/paired counts stay bound to validated reports; raw quotes/enrolments remain machine-only. Local screenshot review was unavailable; DOM rendering was verified.

Publication verified at /performance: deployed JS contains the new panel and frozen protocol. The first entry job completed successfully in run 43497520575; report seq223057 at 20:08:40.480975 Dublin, received 20:08:40.611907. It enrolled 16 cohorts: each arm has eight blocked; ask-trigger has six unfilled/two open, bid-confirmed seven unfilled/one open. Zero closes/paired outcomes. Five CHYM quote-error polls remain visible. Eight of nine jobs passed; comparison-watcher correctly failed for an unrecovered stale CHYM IEX quote. Do not call the entire workflow green. The exact live report passes the browser parser; replay of all 359 source events reproduces it exactly (source digest 99dfb0bc3a9b32f0789adf79ca69184bdeeff69b505e642689926eee69edebd3). No profitability conclusion. See [frozen entry protocol](experiments/entry-confirmation-v1.md).

## Execution-history reporting repair (13 November, 20:13 Dublin)

Separate execution/readiness runs failed after combined source journals crossed their 50 MB raw-history ceiling (run 43496441892, job 132130666653). This predates the entry experiment. Execution/readiness alone is now pinned to `abe1948321ee031b688a0e8e41d03881182e61ef`; its bounded disk archive preserves all events, stable replay order, canonical source hash and original protocols. Existing daily validation, a 1 GB/one-million-event aggregate bound and workflow timeouts still apply. Readiness stamps probes after replay. No budget reset or history deletion occurs.

CI [43498939661](https://github.com/Chiizzie/market-radar-ai/actions/runs/43498939661) passed. A real 49,420-event replay reproduced the entire previous execution report, all six portfolios and trade-evaluation report exactly. See [history capacity repair](incidents/2026-11-13-execution-history-capacity.md). Production verification succeeded in [43499371328](https://github.com/Chiizzie/market-radar-ai/actions/runs/43499371328), job 132140814855: 65,863 source events / 63,605,555 canonical bytes replayed, lossless export restore verified, execution published, readiness published, daily trade evaluation and artifact upload all passed. Execution seq227273 as-of20:14:19.929077, receipt20:14:54.519996; readiness seq228309 as-of20:16:12.112959, receipt20:16:19.891757 Dublin. At20:17:46 the evidence helper validated known schemas/bindings/counts: 11 operational passes and one existing AI allowance block (EUR0.129096 remaining versus EUR0.15 required). The helper does not independently authenticate source evidence. Live trading readiness and profitability remain unestablished; broker costs, incomplete AI-cost attribution and one unresolved hypothetical USD/code position remain evidence limits. Future checkpointing is needed before the larger bounds/time limits are reached.

## Current reliability repair (13 November, 21:06 Dublin)

This section supersedes earlier runtime pins above. Storage retry, authenticated prefix recovery, split entry enrolment/observation and current-job readiness fixes have passed their source CI and real-history replay. See [runtime reliability repair](incidents/2026-11-13-runtime-reliability.md) for exact pins and evidence. The repaired natural run 43508253631 completed successfully, with all ten job conclusions successful and authenticated watcher startup 6.109 seconds. It ran after regular close; entry/strategy workers were session-skipped and zero fresh comparison quotes were observed. See the incident receipt before inferring active-session readiness. No risk, budget, feed subscription or strategy protocol changed. Active-session quote/queue validation remains for the next session.

## Knowledge proposal

The user asked about strengthening the scanner with skills and knowledge. [The concrete proposal](scanner-knowledge-improvement-proposal.md) records the checked current reviewer path, a proposed versioned playbook/case-retrieval milestone, primary-source catalysts, point-in-time rules and acceptance measurements. This is a proposal, not an installed skill or deployed reviewer change. Preserve current strategy protocols and budgets while evaluating it.

Deployment verification: the **knowledge-shadow job succeeded** in the regular [21:55 scan, run 43514885887](https://github.com/Chiizzie/market-radar-ai/actions/runs/43514885887/job/132194660782). At 21:56:25 Dublin it correctly reported `outside_validation_period`, zero model calls and no trade authorization, then saved artifact `knowledge-shadow-43514885887` (ID 14080970729). This verifies the installed worker and period guard; it is not a fresh-market paired decision or a claim that the entire still-running scan completed. [Deployment receipt](evidence/knowledge-deployment-20261113.json).
