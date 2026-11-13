# Market Radar AI: continue here

Last verified: 13 November 2026; knowledge preparation worker succeeded in the 21:55 scan, reporting at 21:56:25 Europe/Dublin. First repaired reliability run completed at 21:17:12. Active-session coverage remains unverified. Refresh source and production evidence before editing.

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
