# 13 November 2026: review reliability and evidence milestones

All times are Europe/Dublin (UTC on this date). This records engineering changes and research evidence, not demonstrated profitability.

## Implemented changes

- Budget ledger: compact encoding preserves every identity, reservation, charge and usage receipt. The 17:20 failure was a 500,000-byte storage ceiling, not an exhausted AI allowance. The observed file was 499,869 bytes; equivalent compact JSON was 383,627 bytes. No limit or charge was reset. This restores capacity; it is not an unlimited storage migration.
- Attempt and cooldown bookkeeping is now one atomic compare-and-swap write instead of four. Confirmed short GitHub throttles may retry the identical rejected write. Ambiguous transport/5xx failures and unclassified permission refusals remain closed. Safe diagnostics retain status/reason without credentials or provider bodies.
- Paid reviews have compact response bounds. Incomplete model output retains its billed usage and receipt, becomes an explicit `review_incomplete` warning, never becomes an approval, and is not automatically retried with another paid call.
- Every completed role records cost, tokens and elapsed time. Signed dashboard ingestion accepts the exact new prompt version and validates stage identity, timing and metadata.
- A separate read-only report traces enrolment, observed quotes, review start, decision, expiry and entry. Missing quotes, an incomplete review, a rejected decision and an untriggered watch remain distinct.
- The frozen strategy experiment now reports volume and net-reward blockers, the target cap responsible, and observed quote excursions around closed outcomes. Original strategy inputs, parameters, fills and outcomes remain unchanged.

Core runtime: `81cced2458813dc0426c71f20da3f85d52a7fa3f`.
Strategy diagnostics: `fc12be18156a2ebbef2141275bf07f3962655e71`.
Dashboard contracts: `1793d4fe146e05659dd09a48f0d394fe5b5ec57c`.

The original `market-radar` repository, live-order settings and AI budget amounts were not changed. No paid Lovable editing agent was used.

## Frozen reviewer comparison

Protocol: `058fb15fdd9b8d3948db4669bb564e589df8e98cb67a30b607fc6ec5dacc12ad`.
Prompt: `paper-compact-evidence-20261113-v2`.

Use the first attempted qualifying setup per symbol per day under this prompt, retaining failed attempts. Compare code-only selection, the existing independent chief's initial assessment before seeing peers, and the full team's existing approval policy. Reuse calls already made: zero additional model calls.

All three selections are scored against the same code-only reference outcome. This is a **hypothetical selection comparison**, not an executable single-reviewer strategy or a measured latency improvement. Actual post-approval AI outcomes remain separate. Calls with missing usage have unknown cost. Unfilled, open, incomplete and unresolved outcomes are never silently converted to zero-profit closed trades. Independent experiment arms overlap and must not be added together.

Do not tune this comparison after seeing winners. Before recommending a simpler live workflow, require later-day evidence, actual prospective fill/latency validation and positive results after costs; no sample size alone establishes an edge.

## Evidence from today's runs

Source run: https://github.com/Chiizzie/market-radar-ai/actions/runs/43471791146

- Replayed 4,513 strategy events through the new diagnostic code: all 91 frozen cohorts and every variant's results reproduced exactly.
- Same-time-volume ATR USD arm: 81/91 cohorts had `net_reward_below_2r`. Target cap attribution: 40 six-ATR projections, 20 observed resistance caps, 21 three-stop-distance caps. Blockers overlap: 61 also had relative volume below one. No closed ATR outcomes in this snapshot.
- Structural USD controls had distant projected targets: median about 7.97 ATR. Rolling-volume control had three closed stops, net about -EUR11.73; same-time-volume control had four, about -EUR13.88. These are overlapping simulations, not separate portfolio losses. The three shared losses were ZTO, STNE and ARR; CG was the extra same-time-volume loss.
- ZTO and ARR had no positive observed bid excursion from the modelled entry; STNE reached about +0.68R before stopping. These are sampled reference quotes, not intrapoll extrema or broker fills. A wider stop cannot be assumed to fix selection or target realism.
- The 17:22 source comparison snapshot had 70 cohorts: code-only 59 not filled, four watching, four open, one unresolved and two closed. Thirteen review attempts included eleven completed reviews (median 41.42 seconds) and two incomplete. Four completed decisions approved watches: RIG, KC and IVR remained unfilled; BRBR was an open simulation. Approval is not proof of entry or profit.
- A comparison watcher saw twelve stale CDNL quote failures and a maximum observation gap of about 54.39 seconds. This remains a real data-quality failure; the quote rules were not weakened to make its job green.

### Opening experiment checked in its actual window

Runs 43445744470, 43446548969 and 43447339258 checked 79 candidates at 14:46:55, 14:51:33 and 14:56:23. Each enrolled zero. Blocker occurrences overlap and are not unique missed trades.

| Reason | 14:46 | 14:51 | 14:56 |
|---|---:|---:|---:|
| Opening direction not confirmed | 30 | 52 | 54 |
| Turnover below USD1m on the observed venue | 32 | 30 | 38 |
| Invalid/incomplete opening bars | 28 | 15 | 10 |
| Current reference quote missing | 18 | 15 | 11 |
| Completed-bar breakout already passed | 0 | 10 | 12 |

NVDA, AMD, MU and INTC failed opening direction at all three checks. This is evidence for this date only. IEX venue turnover is not consolidated US-market turnover. The separate volume/ATR continuation experiment requires twenty completed five-minute bars (100 minutes), so it cannot cover the first opening surge. Its rule was not changed mid-experiment.

## Validation and remaining evidence

- Core: 1,541 offline tests passed, compilation and both synthetic protocol rehearsals passed. A subsequent trace-label clarification passed its 17 focused comparison tests.
- Strategy: 34 focused tests passed, including partition isolation and unchanged outcomes; real-event replay matched exactly.
- Dashboard: 697 offline tests passed across the final checks; TypeScript and production build passed. The live RLS suite could not run locally because its environment file was unavailable; no access controls were changed.
- Diagnostic reports are stored in separate signed database partitions and workflow artifacts. They are not a new visible dashboard panel.
- Still required: verify the deployed run, collect fresh completed outcomes, validate reference quotes against broker execution evidence, and resolve observation gaps. Ledger storage still needs eventual durable expansion. Profitability and autonomous live trading are not established.

## Deployment verification after chat continuation, 18:14 Dublin

The first full review under the repaired pinned runtime was observed and checked in this session; no additional review was manually dispatched.

- Workflow definition: `cf94b60507f2dd5a32b69e15d29cef50cedcce2a`; natural run [43479136120](https://github.com/Chiizzie/market-radar-ai/actions/runs/43479136120), dispatched at 18:05:10 Dublin. Collection, review, paper watcher, account sync, method shadow, market context and strategy experiment succeeded. Comparison watcher failed on real stale reference quotes. The complete workflow is therefore **not all-green**.
- Paid review job [132071382442](https://github.com/Chiizzie/market-radar-ai/actions/runs/43479136120/job/132071382442) used runtime `81cced2458813dc0426c71f20da3f85d52a7fa3f`. All eight stage receipts were present under prompt `paper-compact-evidence-20261113-v2`, costing EUR0.043773. IP received `PAPER_WATCH_FOR_ENTRY` at 18:07:51.931087. Dashboard receipt is 18:07:56.386398, archive `14f592a47952a4a8c1b6fed149985635899fbd81ce4780493e708b0e7758efb0`. Final archives are stored in `candidate_reviews`, not the older `paper_reviews` table. Both dashboard and existing Telegram delivery were confirmed by the run artifact; no new message was sent during this continuation.
- Decision artifact `14064397973` was downloaded and its SHA256 matched the job log: `d2ac7f1985509bcf08d6df525327b036a126e902b5bb0babb5e09461eb5f357c`.
- Decision-evidence database seq `170604`, occurred 18:11:13.797453, received 18:11:14.222013: 136 traced cohorts; one first attempt under the new prompt, IP. Code, independent chief and full team all selected it; baseline and actual AI outcome were both `not_filled`. The independent chief cost EUR0.005178; full review cost EUR0.043773. There are **zero matched closed outcomes**. This verifies cost accounting and comparison operation, not profitability or an executable simpler workflow.
- Strategy-diagnostics database seq `169698`, occurred 18:09:01.886052, received 18:09:02.116096: 136 frozen cohorts. Both USD ATR arms had 125 net-reward-below-2R blockers: 66 six-ATR target caps, 24 observed-resistance caps and 35 three-stop-distance caps. The same-time-volume arm also had 92 low-volume and two unavailable-volume blockers; counts overlap. It had 131 blocked, four not-filled and one open case, with no closed outcome. Structural USD target distance was a median 8.22 ATR. Diagnostics explain the constraints; they do not justify loosening them.
- Comparison watcher job `132070745485`: 64 polls, 682 quotes, six stale-quote failures across MFG and OCUL; maximum measured polling gap about 5.74 seconds. MFG recovered; an OCUL stale-quote gap remained at worker finish. These are source-data gaps, not evidence that the polling worker stopped. Source timestamp checks remain enforced, and missing observations are not invented. No provider-wide outage is established.
- Compact ledger was independently read at approximately 18:10: 387,354 bytes, 1,029 entries and six unsettled reservations, with the same EUR1/day, EUR10/month and EUR100 lifetime limits. This confirms the repair preserves spending history and capacity. It does not solve unlimited future ledger growth.
- Fresh verification on exact deployed sources: 156 focused core/review/ledger/comparison tests passed; 34 strategy/diagnostic tests passed. The earlier full-suite evidence above is retained separately; these checks do not claim a second full-suite run.
- Unmodified same-day readiness/execution payloads (seq 168448/168273) were checked with the evidence helper at 18:08:25 Dublin. Its structural checks passed; readiness remained `attention_required`. Cumulative execution portfolios since 12 November remain separate from today's strategy experiment and are not added to it.

## Remaining measurable work

1. Diagnose source coverage for stale/missing/wide IEX quotes against a contemporaneous independent or broker reference before changing providers, budgets or any freshness/spread rule. Preserve the failed sessions. A different source policy requires a new prospective experiment.
2. Let the frozen volume/risk/cost and reviewer-selection experiments gather later unseen sessions, retaining unfilled, open, incomplete and unresolved cases. The new reviewer comparison has one unfilled case; it cannot establish that six reviewers earn their cost or that a single-reviewer path is executable.
3. Add durable ledger growth/rotation with atomic reservations, preserved historical receipts and cross-version reader compatibility before this compact file reaches its unchanged 500,000-byte ceiling again. No spending limits are to be reset.
4. Make the signed diagnostic reports visible in the existing Performance interface if desired; ingestion is deployed, but these diagnostic partitions currently have no dedicated panel. Ordinary watch/archive display is working.
5. Broker-reference validation and demo order lifecycle remain later, separate milestones. No actual broker fills, live-order permission or profitable strategy have been established.

For the next development conversation, start with [CONTINUE-HERE](../CONTINUE-HERE.md) and re-read current runtime pins and latest receipts. Do not recommit a whole earlier dirty checkout.
