# Volume, risk and cost experiment deployment

12 November 2026, Europe/Dublin. User approval covers the isolated paper experiment and its dashboard integration. Direct GitHub edits are preferred to paid Lovable editing-agent calls.

- Producer runtime: `73d880261768b32453986d7da717058810178920` (155 focused tests passed, including 30 experiment tests; CI run 43259903724).
- Protocol: `c796287f67ef1be3a30d2dcdb1cdea8183e8ec75eb34a5bc9885b480ad2059b1`.
- Dashboard: `Chiizzie/pixel-perfect-replay-32614` commit `065cc4801196e137ee1aafda0b58156684416b27`. Direct contract repairs passed 681 offline tests, TypeScript and production build. No further Lovable editing-agent call was made. Publication requested using deployment `f58dbce8-b7e5-4c23-9dbc-9c6012dc1514`; at 17:12 Dublin the live `/performance` page served `/assets/performance-B6S69pZI.js`, containing the repaired panel and conditional activation wording.
- The database migration is already applied. Raw enrolment, screen and quote events are private; only validated reports are available to viewers. Synthetic fixtures were used only offline.
- The new scheduled job is enabled unless repository variable `STRATEGY_EXPERIMENT_ENABLED` is exactly `false`. Setting it to `false` pauses new experimental workers. Existing collection, review, watcher, context and account jobs are unchanged byte-for-byte as parsed YAML.
- The new job uses only market-data and signed-storage credentials. It receives no model, Telegram or order credentials and is independent of ordinary trading alerts. An experimental failure remains visible but does not stop normal collection.

This workflow commit enables the worker for subsequent ordinary dispatches. Actual enrolments, quotes, completed reports and ordinary job status must be verified before claiming the first run passed. 12 November is a partial commissioning session; full-session validation starts only after actual activation. No profitable edge is established.
