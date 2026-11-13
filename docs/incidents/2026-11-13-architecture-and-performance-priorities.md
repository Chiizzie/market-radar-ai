# 13 November 2026: architecture and performance priorities

Evidence checked around 17:10–17:15 Europe/Dublin. This is an architecture recommendation and report audit; no strategy, deployment pins, budgets, runtime skills or hosting were changed.

## Recommendation

Use a dedicated ChatGPT Project to keep development conversations, repository links, constraints and evaluation decisions together. Keep GitHub as the versioned code source. A Sites dashboard is possible, but migration is not justified by the current performance evidence. A dashboard migration would not change quote quality, eligibility, entry timing, target construction or the paid-review path.

Continue direct repository development without the Lovable AI editor. Moving the interface does not remove the scheduled review's model calls. A future move to a persistent worker and transactional operational storage should be assessed against measured worker gaps, latency and ledger failures, with explicit cost estimates.

The installed personal audit skill supports development and evidence review. It is not loaded by the scheduled six-reviewer runtime. Runtime improvements require focused, versioned instructions/tools/code and their own evaluations; copying all audit instructions into every specialist is not a trading-method upgrade.

## Current revisions and evidence

- Main workflow read today: `.github/workflows/scheduled-scanner.yml`.
- Collection/review/tracking runtime: `3a113a4e8c4e03e9b28799c146db1f1cae6f987a`.
- Volume/risk/cost experimental runtime: `73d880261768b32453986d7da717058810178920`.
- Experiment: `c796287f67ef1be3a30d2dcdb1cdea8183e8ec75eb34a5bc9885b480ad2059b1`.
- Lovable project: `97051425-8afb-4ea6-bf3e-f6e5fc127ba3`; SELECT-only reads from `research_events`.
- Strategy report seq 156543, day 2026-11-13, as_of 17:12:54.119438 UTC.
- Previous commissioning-day strategy report seq 140091, day 2026-11-12, as_of 21:09:12.396463 UTC.
- Execution report seq 156123, as_of 17:10:12.432654 UTC, protocol `010dac634261525d61b6e4acf6a822bbae80f3adb0b2565b361b038b39ab1618`, cumulative since 12 November.
- Readiness report seq 156218, as_of 17:10:18.402989 UTC.
- Offline assessment of unmodified readiness/execution payloads completed at 17:14:55 UTC. It checked schemas, protocol bindings, ages and counts, not source-event replay or broker fills.

## Findings

The latest experiment screening examined 79 stocks: 31 were blocked by reference spreads above 20 bps, 27 by an already-passed trigger, and six were newly enrolled. These are one-screen first-blocker counts, not whole-market opportunity or missed-profit counts. Broker/consolidated spread comparison is needed before declaring the spread blocks incorrect. Trace trigger timestamps before attributing passed triggers to latency.

The experiment had 74 first-eligible symbol cohorts today. Separate independent variants, not additive account portfolios:

| USD-cost variant | Closed | Wins / losses | Closed net EUR | Other outcome states |
| --- | ---: | --- | ---: | --- |
| Rolling volume, structural stop | 3 | 0 / 3 | -11.7252 | 47 blocked, 18 not filled, 2 open, 1 unresolved, 3 watching |
| Same-time volume, structural stop | 4 | 0 / 4 | -13.8849 | 52 blocked, 15 not filled, 1 open, 2 watching |
| Rolling volume, ATR risk | 0 | 0 / 0 | not established | 72 blocked, 1 not filled, 1 open |
| Same-time volume, ATR risk | 0 | 0 / 0 | not established | 72 blocked, 1 not filled, 1 open |

These overlap, use IEX reference quotes and assumed costs, and are not the exact production AI strategy or brokerage fills. Do not add their P/L or trade counts. Small, partial-day results cannot establish superiority, failure of all strategies, or profitability. Keep the current protocol frozen.

Source inspection confirms 20 completed five-minute same-session bars are required. This continuation experiment cannot enroll before about 16:10 Dublin on 13 November, and does not test the opening surge. The existing separate opening-method experiment needs its own assessment.

Structural-control targets are adjusted until the cost/risk calculation meets 2R. ATR targets are capped by resistance and volatility distance. Test target attainability and blocker causes; a numerically acceptable reward/risk ratio is not evidence that a target is likely to be reached.

The separate cumulative execution comparison has zero closed AI-reviewed USD-profile trades: 10 expired, one invalidated and one open among 12 considered approvals. The code-only USD book has one closed outcome (-4.3767 EUR), one unresolved and many capital blocks. AI cost attribution is incomplete for 320 source cohorts. These reports do not yet establish that six paid reviewers improve outcomes.

## Operational incidents already diagnosed

- [16:30 run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43463395764): sceptic response incomplete after 1,024 output tokens; known usage settled.
- [16:50 run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43466713147): HTTP 403 saving the cooldown/budget record before paid calls. Exact refusal cause absent from logs.
- [16:55 run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43467532135): all jobs succeeded; paid review completed with eight calls.
- Other seven jobs, including the new experiment, passed in both failed runs. Recovery is not a permanent fix.

## Next measurable milestone

1. Repair and reproduce the two operational failures; retain provider receipts and distinguish throttling, permission refusal and incomplete model output without automatic paid retries.
2. Replay the selected spread and passed-trigger cases using timestamps and evidence available at the decision. Report real disqualifications, data disagreements, discovery delay, review delay and missed observation separately.
3. Explain every ATR variant's block, and assess existing opening-method results separately. Preserve unfilled, unresolved and failed cases.
4. Freeze a focused runtime-review comparison against code-only and a simpler review path. Score correctness, observed entries, net outcomes, missed opportunities, latency and AI costs on later sessions.
5. Consider hosting or data-provider migration only where a measured limitation survives these checks.

Official product references:
- https://learn.chatgpt.com/docs/web
- https://learn.chatgpt.com/use-cases/build-and-deploy-internal-apps
- https://developers.openai.com/plugins/concepts/skills
