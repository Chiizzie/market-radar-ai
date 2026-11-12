# Volume, risk and cost experiment deployment

12 November 2026, Europe/Dublin. User approval covers the isolated paper experiment and its dashboard integration. Direct GitHub edits are preferred to paid Lovable editing-agent calls.

- Producer runtime: `73d880261768b32453986d7da717058810178920` (155 focused tests passed, including 30 experiment tests; CI run 43259903724).
- Protocol: `c796287f67ef1be3a30d2dcdb1cdea8183e8ec75eb34a5bc9885b480ad2059b1`.
- Dashboard: `Chiizzie/pixel-perfect-replay-32614` commit `065cc4801196e137ee1aafda0b58156684416b27`. Direct contract repairs passed 681 offline tests, TypeScript and production build. No further Lovable editing-agent call was made. Publication requested using deployment `f58dbce8-b7e5-4c23-9dbc-9c6012dc1514`; at 17:12 Dublin the live `/performance` page served `/assets/performance-B6S69pZI.js`, containing the repaired panel and conditional activation wording.
- The database migration is already applied. Raw enrolment, screen and quote events are private; only validated reports are available to viewers. Synthetic fixtures were used only offline.
- The new scheduled job is enabled unless repository variable `STRATEGY_EXPERIMENT_ENABLED` is exactly `false`. Setting it to `false` pauses new experimental workers. Existing collection, review, watcher, context and account jobs are unchanged byte-for-byte as parsed YAML.
- The new job uses only market-data and signed-storage credentials. It receives no model, Telegram or order credentials and is independent of ordinary trading alerts. An experimental failure remains visible but does not stop normal collection.

This workflow commit enables the worker for subsequent ordinary dispatches. Actual enrolments, quotes, completed reports and ordinary job status were verified below. 12 November is a partial commissioning session; full-session validation starts only after actual activation. No profitable edge is established.

## First complete run verified, 17:26 Dublin

[Run 43267450568](https://github.com/Chiizzie/market-radar-ai/actions/runs/43267450568), dispatched at 17:15:18, completed successfully at 17:24:06 with all eight jobs passing, including the unchanged seven normal jobs and the isolated experiment. First durable enrolment arrived at 17:18:29. The first published experiment report is database sequence 91065, as-of 17:24:02.307937 UTC/Dublin, received at 17:24:02.665949.

The report tracks 15 common symbol/day cohorts across ten separate variants. This worker completed 66 polls, recorded 159 quotes, reported zero error polls/capacity deferrals and a maximum polling interval of 5.846737 seconds. The 17:20 overlapping worker had already added additional cohorts to the shared journal. At this snapshot both rolling structural cost arms have one open simulated entry; no arm has a closed outcome. All ATR variants are blocked at this early snapshot. Results remain unproven and are not alerts or broker fills; alternative arms must never be added together.

The exact production payload passed the dashboard parser, including the database day/time binding. It contains 100 detail rows and explicitly reports 50 omitted rows; aggregate per-variant counts cover all 15 cohorts. Artifact 13966269650 was downloaded, its ZIP SHA256 verified as `fd85089f9f012eef9f64d1d3e07b677d30fe61b9dabff2efc6ae50e3ea6d79a0`, and all 248 saved event hashes and deterministic cohort replays were checked. Rebuilt full report and paired-result artifact match exactly; the report artifact also matches the database payload. Retention expires 12 December 2026.

Full backend CI [43268192773](https://github.com/Chiizzie/market-radar-ai/actions/runs/43268192773) and focused experiment CI 43268184957 passed at source-branch checkpoint `2338134f06a4dfaff038b524489e8b73d7d6d60b`. All 1,557 backend tests passed locally after fixing two stale test assumptions (former EUR5 lifetime cap and absent main-workflow fixture). Those fixes change tests/workflow source availability only; the deployed experiment runtime remains the tested `73d880261768b32453986d7da717058810178920` and live allowances are unchanged.

Next measurable milestone: accumulate later complete sessions, inspect closed/unfilled/unresolved outcomes and quote coverage per variant, then compare volume/risk/cost effects on matched cohorts without tuning to commissioning results. Do not promote these paper variants into ordinary alerts or live execution from this operational pass.
