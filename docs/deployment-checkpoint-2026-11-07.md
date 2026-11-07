# Deployed milestone checkpoint — 7 November 2026

Latest verification at 16:11 Europe/Dublin. EUR, paper-only, EUR20 maximum planned loss and existing intraday rules remain in force.

## Market/sector context and same-time volume — verified 16:11 Europe/Dublin

- [Backend PR #16](https://github.com/Chiizzie/market-radar-ai/pull/16) and [dashboard PR #10](https://github.com/Chiizzie/pixel-perfect-replay-32614/pull/10) merged. Exact tested backend source: `9cbc4b94be12b843aae1621ad6e5efe4a33dacf6`; backend merge `2167a868e2d8ba0ba46ba277f3dfa427fdf2cd8e`. Deployed dashboard merge: `9d4726a968c14d3ec38cdb786d95fb529c3af634`.
- The [Performance dashboard](https://pixel-perfect-replay-32614.lovable.app/performance) now has a protected market context panel: SPY plus eleven sector ETFs, completed-session-window returns, stock relative performance against an explicitly selected benchmark, same-time cumulative relative volume, sample dates, coverage counts and missing/stale evidence. Company sector membership is not automatically verified; choosing a sector ETF does not establish a company's classification.
- An independent research worker examines up to 40 stocks already in each current capture. This is stock context, not a new universe-wide discovery pass or crypto coverage. It uses completed five-minute IEX bars with split adjustment, exchange-calendar sessions and a 30-second settling allowance. Relative volume compares the same elapsed regular-session window against up to ten prior full sessions, requiring at least five complete historical windows. Missing bars are unknown, never zero; overnight gaps are excluded from session returns.
- Daily bounded history caching reduces repeat provider work. Actual calendar closes, New York daylight saving changes, incomplete history, stale/future evidence, invalid bars, pagination and cache corruption are handled explicitly. IEX covers a partial venue, so these figures are not consolidated US-market volume.
- Migration 0009 is applied. Rollback rehearsals checked viewer-only derived evidence, nonviewer exclusion, private raw records, and append/read-only service privileges. No synthetic rehearsal records remain. The live page returns HTTP 200 with viewer sign-in; an unsigned machine read returns HTTP 401.
- The new independent `market-context` scheduler job is pinned to the tested source. Activation: `171f273bc66d0b1e585c619098f9989ef4be0c47`. All five existing scheduler jobs were preserved: collector/reviewer/watcher/method-shadow remain pinned to `76348883041c5416fdf0fd674b7668f1414239ac`, account-sync to `afd5a0121bfdea8f5186f261bcca9e79a8d21879`. Context does not delay the review dependency chain.
- Health reporting now recognizes the independent context job; health activation `43597df5a505115adbad5cb09431c9b53f36ed5b`. [Live health run](https://github.com/Chiizzie/market-radar-ai/actions/runs/42389575923) succeeded and stored real metadata with `source_status=received`.
- Exact-source [backend CI](https://github.com/Chiizzie/market-radar-ai/actions/runs/42389257408): **1,272 tests passed**, compilation and both offline team scenarios passed. Dashboard: **592 offline tests**, TypeScript and production build passed. This includes Python-to-dashboard evidence contracts, arithmetic, session/cutoff validation and rejection of historical rehearsal data as forward evidence.
- [Production provider/storage verification](https://github.com/Chiizzie/market-radar-ai/actions/runs/42389577422) succeeded. It published one genuine Saturday forward-status report at **16:06:28 Europe/Dublin**, with `outside_regular_session`, no completed bars and no invented stock selection. Database inspection confirmed 12 unavailable benchmarks, zero stocks, zero model calls and false trade/strategy authorization.
- The same verification run separately read the real **6 November** completed session for ASH, AAPL, MSFT and the 12 benchmarks. Across 78 five-minute buckets, it produced usable same-time volume measurements for **2/3 stocks and 11/12 benchmarks**, using eleven bounded bar-batch requests. Incomplete data remained unavailable. This was an artifact-only historical provider rehearsal, not a strategy backtest or forward result; it was not published into the forward research database.
- Context protocol: `71c7f19ecb947afb6134954df9e9bc691830d74cd403c382210a3706c8ee9cc5`. Existing comparison protocol `4a0bfb1b110061c801edae8267223ff64c356f7bc72021638e37b48d918458c2` and AVWAP protocol `a8afeedf54f633f0324380cd5816fdbdd7604f35b801272912e2de94f0592ea4` are unchanged. No AI prompts, qualifying rules, ranking, costs, risk limits, Telegram alerts or orders consume this new evidence.
- Both research cohorts remain empty: no enrolment, method-enrolment, quote or review events were added. This verification proves data collection and storage, not trading performance. The original scanner remains untouched at `cbfdb401b451bac8efc83d4bbe3104de8d6a25d2`.

Implementation and source references: [market-context-volume.md](https://github.com/Chiizzie/market-radar-ai/blob/phase-1/market-data-layer/docs/market-context-volume.md).

Still needed: verify ordinary scheduled context capture during a live weekday session, review the effects of partial-venue/missing-bar coverage, complete natural paper qualification/entry/exit, and collect later unseen outcomes. Any use of context in strategy decisions needs a separate versioned comparison. Realistic cost estimates, portfolio constraints and sustained recovery/quote coverage remain later milestones.

## Research history, exposure and health — verified 15:21 Europe/Dublin

- [Backend PR #15](https://github.com/Chiizzie/market-radar-ai/pull/15) and [dashboard PR #9](https://github.com/Chiizzie/pixel-perfect-replay-32614/pull/9) merged. Exact tested backend source: `76348883041c5416fdf0fd674b7668f1414239ac`; backend merge `5895924a8a4d9400b605965f05f7c9d7d1fe43bd`. Dashboard deployed merge: `210742dc83e6cc77591ca2033787c610d2a4156f`.
- [Performance dashboard](https://pixel-perfect-replay-32614.lovable.app/performance) now browses 30 historical days per page, separately by protocol, with immutable per-setup entry/exit, review, cost and blocker details. Older records without details remain explicitly incomplete. Current health remains independent of the selected historical day.
- Paper exposure includes simultaneous entry capital and initial stop risk for each alternative arm, with unresolved positions retained as possible exposure. This is reporting only: no capital gate, correlation model, strategy changes or portfolio-return claim.
- Migration 0008 applied after rollback checks of date/detail pagination, late-arrival ordering, immutable snapshot isolation and viewer/nonviewer RLS. Raw events remain private; service-role access remains append/read only. All rehearsal records were rolled back.
- Collector, reviewer, watcher and AVWAP pins now use the exact tested source above. Scheduler activation: `3d073ab34d863fe8291dff485d68d05e346513d5`. Existing account-sync pin remains `afd5a0121bfdea8f5186f261bcca9e79a8d21879`. Original scanner remains `cbfdb401b451bac8efc83d4bbe3104de8d6a25d2`.
- New independent health workflow activation: `696717f7c4f4df86743aa2a2d87993e70551d96e`. It reads real GitHub run/job metadata, runs after completed scanner workflows and on a weekday monitoring schedule, and makes no model, quote-provider, order or Telegram calls. Missing or old evidence is not labelled a successful scan.
- Exact source CI [42385473537](https://github.com/Chiizzie/market-radar-ai/actions/runs/42385473537): **1,258 tests passed**, compilation and both offline team scenarios passed. Dashboard: **574 offline tests**, TypeScript and production build passed. Signed partition mismatch and real Python output contracts passed, including AI-approved and AI-rejected outcomes.
- Live comparison verification [42385778918](https://github.com/Chiizzie/market-radar-ai/actions/runs/42385778918): signed storage, duplicate receipt, independent reconstruction and JSONL restore passed on the actual empty cohort; two source events exported. [Recovery upload](https://github.com/Chiizzie/market-radar-ai/actions/runs/42385778918/artifacts/13579870912) confirmed and recorded.
- Live AVWAP verification [42385780919](https://github.com/Chiizzie/market-radar-ai/actions/runs/42385780919): equivalent storage/restore checks passed on the actual empty cohort; three source events exported. [Recovery upload](https://github.com/Chiizzie/market-radar-ai/actions/runs/42385780919/artifacts/13579890760) confirmed and recorded.
- Live health verification [42385782010](https://github.com/Chiizzie/market-radar-ai/actions/runs/42385782010): metadata received and complete job list stored. Latest natural scanner run was Friday, with successful collection, review, watcher and account-sync jobs; this is execution evidence only.
- Current database: both cohorts **0 enrolled**, closed P/L **null**, exposure **0**, complete zero-row detail references, two genuine recovery-upload receipts and one operational report. No synthetic trade records were inserted. Live unsigned machine read returns **401**; the performance page returns **200** and requires viewer sign-in.
- Both verification workflows made **0 paid model calls, 0 provider quote calls, 0 trades and 0 Telegram messages**. Archive compression integrity was checked locally in those runs. Receipts confirm upload, not a later download-and-restore test or continuous artifact availability.

Implementation: [research-history-health.md](https://github.com/Chiizzie/market-radar-ai/blob/phase-1/market-data-layer/docs/research-history-health.md).

Still needed: natural-market qualification/entry/exit and sustained quote coverage, scheduled end-of-session backups under load, and enough later unseen outcomes to measure performance. Market/sector context, same-time historical volume, more realistic costs and portfolio constraints remain separate research milestones. Existing comparison and AVWAP protocol hashes are unchanged.

## AVWAP shadow milestone — verified 14:40 Europe/Dublin

- Implemented and enabled a separate stock-only, long-only session-open AVWAP reclaim experiment. It uses completed fifteen-minute and prior-day trend checks, EUR20 maximum planned loss, independent fictional EUR500 allocations, and fixed cost assumptions. No trader-copying feed, AI reviews, Telegram alerts or orders are added.
- Rules and limitations: [anchored-vwap-shadow.md](https://github.com/Chiizzie/market-radar-ai/blob/phase-1/market-data-layer/docs/anchored-vwap-shadow.md).
- Backend PRs [#13](https://github.com/Chiizzie/market-radar-ai/pull/13) and [#14](https://github.com/Chiizzie/market-radar-ai/pull/14) merged. Final tested source: `3910f1b1bf91a6cfe5f81ed7ff846ba75b36afa9`; tree `397a8dc6cc3c9072b9d4a7063e5339ad3859fcc4`.
- New `method-shadow` job is pinned to that source. Main activation commit: `3017b31a37e4a1bb0ed8a193d3f0babf7cb04c7b`. All pre-existing scheduler jobs were verified byte-for-byte unchanged, including source pins.
- Dashboard [PR #8](https://github.com/Chiizzie/pixel-perfect-replay-32614/pull/8) merged; deployed final copy clarification commit `2d0023e7b8414bec43078d0189aa3628af32506e`. Published method panel and viewer sign-in prompt verified at /performance.
- Database migration 0007 applied after rollback rehearsals of concurrent first-enrolment uniqueness and privileges. Viewer summaries only; raw scenarios/quotes require signed machine access. Existing event permissions remain insert/read-only for the service role.
- Protocol: `a8afeedf54f633f0324380cd5816fdbdd7604f35b801272912e2de94f0592ea4`. Full-session opening data is required; missing anchors never silently become rolling VWAP. One prospective setup per stock/session; delayed storage rechecks freshness, and concurrent workers preserve the first scenario and expiry.
- Final backend CI: https://github.com/Chiizzie/market-radar-ai/actions/runs/42382485797 — **1,248 tests passed**, compile and offline objection/support scenarios passed. Dashboard: **566 offline tests**, TypeScript and production build passed. The environment-dependent live RLS test was excluded locally; database policy/privilege checks were performed directly.
- Final production signed-storage/recovery check: https://github.com/Chiizzie/market-radar-ai/actions/runs/42382606624 — success on the exact final backend pin. Duplicate append, independent event reconstruction and JSONL restore verified. No provider quotes, model calls, trades or Telegram messages were generated.
- Database check at 14:40: two genuine method summaries, **zero enrolled setups**, zero closed outcomes, net P/L **unknown (null)**. These are storage checks on Saturday, not market-performance results or synthetic trades.
- Original `market-radar` main remains `cbfdb401b451bac8efc83d4bbe3104de8d6a25d2`.

The next natural stock session can begin method qualification only after 90 minutes of completed regular-session bars. Still needed: real method screening coverage, first qualifying enrolment/entry/exit, sustained quote cadence and end-of-session backup arrival. Evaluate later unseen sessions before promoting the experiment; no profitability is established. Actions workers can have gaps and the method only sees the captured subset.

## Previous comparison milestone — verified 14:06
- Backend PR #12: https://github.com/Chiizzie/market-radar-ai/pull/12
- Dashboard PR #7: https://github.com/Chiizzie/pixel-perfect-replay-32614/pull/7
- Scheduler collection/review/watcher source: `9c62a3deb176c9699ac2bb27ac0d504aefb86a3d`; tested tree `6d1df958d04f4336cc536582295531df8d97b48c`.
- Scheduler activation commit: `af97ff2cf9fdbe0ca49faf85b2749fd091c048fe`.
- Dashboard deployed merge: `6b52d2eaf01545637c09eedae1cfb297a0a736f9`.
- Database migration 0006 applied; signed event endpoint live; unsigned POST returns 401.
- https://pixel-perfect-replay-32614.lovable.app/performance loads and requires viewer sign-in.
- 1,233 backend tests, 559 offline dashboard tests, TypeScript and production build passed.
- Backend CI: https://github.com/Chiizzie/market-radar-ai/actions/runs/42379526840
- Production signed-storage verification: https://github.com/Chiizzie/market-radar-ai/actions/runs/42380025744 — successful signed read/write, duplicate-write idempotence, independent reconstruction and JSONL recovery. No AI calls, quote-provider calls, trades or Telegram messages.
- Verification stored one genuine summary of an empty forward cohort: **0 enrolled candidates**. It did not invent trades or backfill earlier runs.
- Main-branch storage verification workflow: commit `18c50c7db17969668582cf728a6bdfa57bfbec44`.

## What is enabled
All code-qualified packets at scheduled review are enrolled before paid selection. An inline observer starts before models; independent watchers recover both baseline and AI arms, including unreviewed/rejected candidates. Comparison evidence lives in immutable PostgreSQL events. Nightly compressed recovery exports are attempted during 22:00–22:15 Dublin, retained 30 days. The existing approved-paper GitHub journal remains separate.

Collection and review now produce a read-only audit against the original scanner's public rolling feed. This distinguishes discovery deferral, missing traces, code/risk blockers and recorded AI decisions, preserving capture-time differences. The original repository was not modified.

## Still to verify from natural runs
- First real eligible enrolment, AI review, observed entry and closed outcome in the new shared comparison.
- A fresh original-scanner signal matched against a production selection trace.
- Sustained quote cadence and capacity under market load, plus end-of-day backup arrival.
- Enough later, unseen paper outcomes to assess net performance and AI contribution. Tests and workflow success are not profitability evidence.

## Trader research
The source policy and proposed method experiments are in [trader-methods-roadmap.md](https://github.com/Chiizzie/market-radar-ai/blob/phase-1/market-data-layer/docs/trader-methods-roadmap.md). No trader-call feed or subscription is enabled. The predefined session-open anchored-VWAP experiment above is now enabled with multiple-timeframe context. Public 13F and Form 4 disclosures are delayed context, not live copying signals; independent track-record verification is still required before describing a source as successful.

Implementation and limits: [forward-comparison-milestone.md](https://github.com/Chiizzie/market-radar-ai/blob/phase-1/market-data-layer/docs/forward-comparison-milestone.md).
