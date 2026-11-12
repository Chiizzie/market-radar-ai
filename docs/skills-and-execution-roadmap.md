# Skills and the next execution milestone

Decision recorded 12 November 2026. Operational timestamps use Europe/Dublin.

## Outcome of the skills review

Created a personal **Market Radar Evidence** skill with a deterministic report-inspection helper and references for deployment auditing, experimental evaluation and broker-demo execution. It improves the development/audit workflow in ChatGPT. It is not loaded by the scheduled Python scanner, does not modify the six paid reviewers and does not authorize orders.

The helper checks known report schemas, evaluation dates, source/experiment bindings, freshness, portfolio counts and unresolved exposure. It keeps alternative portfolios and AI costs separate. It labels input provenance as unauthenticated and the source digest as format-only: source-event replay and connector provenance remain separate checks. Unknown formats are refused.

Validation: 20 automated checks passed. Two independent fresh-context trials used the skill on actual exported reports and a separate synthetic positive-return scenario. Both distinguished operational checks from execution readiness and retained the limits of supplied evidence. No production orders or paid model verification calls were made.

## Existing runtime and current evidence

The actual runtime `e6053db510f0a32f38685351198e42029e852da6` already has role-specific instructions for six reviewers, debate and chief conclusion. Review policy is `paper-specialists-v3-conditional-chief`, prompt revision `paper-scope-clarification-20261111-v1`. Adding generic role names or migrating to another multi-agent framework is not itself an improvement.

At 12:26 on 12 November, the dashboard stored:
- New guarded source `eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8`.
- Execution experiment `010dac634261525d61b6e4acf6a822bbae80f3adb0b2565b361b038b39ab1618`.
- Zero populated cohorts and zero closed trades in this new experiment before the 14:30 regular-session open. This says nothing about legacy counts.
- Ten passed operational checks, a paused out-of-session reference quote probe and pending observation-under-load evidence.
- EUR1 daily configured AI headroom, EUR5.440044 monthly and EUR95.440044 lifetime. The daily cap has reset; these are app-ledger limits, not provider credit.
- Broker costs and the account-currency route remain unverified.

These are a dated snapshot, not a permanent readiness label. See the latest database records and the [prior incident/verification record](incidents/2026-11-11-watcher-startup-and-quote-quality.md).

## External sources worth reusing

- [OpenAI's official curated skills](https://github.com/openai/skills/tree/main/skills/.curated): CI debugging and security workflows are useful development support. They are not measured intraday strategies. The reviewed `gh-fix-ci` workflow targets PR checks and assumes GitHub CLI access; our scheduled scanner needs its own run/artifact workflow.
- [OpenAI skill documentation](https://developers.openai.com/plugins/concepts/skills): reusable workflow instructions and resources, distinct from tool capabilities.
- [Trading 212 API limitations](https://docs.trading212.com/api/section/general-information/api-limitations): Invest/Stocks ISA only; demo/live separation and primary-account-currency execution.
- [Trading 212 API order support](https://helpcentre.trading212.com/hc/en-us/articles/14584770928157-Trading-212-API-key): market, limit, stop and stop-limit order support. Do not infer bracket/OCO atomicity or idempotency.
- [Alpaca paper simulation limitations](https://docs.alpaca.markets/us/docs/paper-trading): paper fills do not fully model latency, queue position or available liquidity.

Review downloaded code, dependencies, permissions and license at a pinned revision. Do not supply brokerage secrets to an unreviewed skill. Existing ChatGPT connectors are not automatically integrations available to the GitHub runtime.

## Concrete progression

### Evidence milestone: a populated guarded forward-session audit

Freeze strategy, prompts and policy while gathering later unseen sessions. Reconstruct naturally eligible setups from the complete immutable events. Measure discovery-to-decision delay, per-symbol observation gaps, entry/expiry/exit coverage, unresolved outcomes, net results under explicit cost scenarios and AI cost. Compare the AI and code-only arms on matching eligible setups; do not combine alternative portfolios or overlapping same-symbol trades into independent evidence.

Demonstrate a real archive download and exact reconstruction, not only an upload receipt. Preserve coverage failures and all historical losses. Predeclare evaluation windows, risk criteria and uncertainty treatment before selecting a winning variant. Neither a green workflow nor a fixed number of trades proves an edge.

### Next engineering milestone: broker-demo order management

Build this while prospective strategy evidence accumulates; demo engineering success is not a live-capital decision.

Default design target is the connected Trading 212 Invest context, subject to confirming demo account/API capabilities. Alpaca paper is another integration test environment, not a substitute for proving the eventual broker's behavior. A CFD goal requires a different supported broker adapter.

Implement a separate persistent order service with:
1. Demo endpoint allowlist and separate credentials; live endpoints disabled.
2. Durable intent/order/fill/position journal and stable intent IDs.
3. Reconciliation of submission timeouts before retry; duplicate-signal suppression.
4. Partial-fill accounting and verified protection quantities; explicit recovery when protection fails.
5. Deterministic trade, daily and combined-risk/capital limits outside model reasoning.
6. Session deadlines, entry kill switch, and restart/feed/database outage recovery.
7. Read-only dashboard order/fill/protection status, with broker acknowledgement distinct from actual fill.

Acceptance demonstration: one complete broker-demo entry-to-exit lifecycle, followed by duplicate signal, unknown submission outcome, partial fill, protection rejection, restart, stale feed and session-close drills. Require final broker positions and journal to agree, no unintended duplicate exposure, and no silently unprotected filled quantity. Exercise missing/failed acknowledgements rather than merely mocking a successful HTTP response.

These tests can begin locally without credentials. Demo account access and desired exposure rules are inputs to later integration, not reasons to activate live endpoints now.

### Unattended real-money consideration

Only consider this after independently reviewable strategy evidence and execution/recovery tests. Confirm broker/account suitability, actual fee/currency route, persistent hosting, monitoring, stop/protection behavior and explicit capital/risk policy. Planned EUR20 risk is not a guaranteed loss ceiling. No arbitrary sample count, return target or agent consensus automatically promotes the system.

No live order submission, live execution activation, runtime strategy change, budget increase or historical-outcome rewrite was made by this skills milestone.

## Engineering implementation and acceptance — 12 November, 14:47 Dublin

The isolated Alpaca paper order-management core is implemented in `src/market_radar_ai/execution/`. **66 focused tests passed in GitHub**, including 30 seeded failure sequences, a real subprocess crash after simulated broker acceptance, backup recovery and replay of a captured broker bracket response.

A complete broker-paper lifecycle passed on core **443b3f7f38e24d8f2cd83c5902ae998878555749**: one-share engineering entry filled, conditional bracket protection recognized, deliberate exit filled, and **zero open orders / zero positions** afterward. This is an engineering fixture, not a scanner signal or profitability evidence.

- [Verified workflow](https://github.com/Chiizzie/market-radar-ai/actions/runs/43240631152)
- [Implementation, earlier attempts and remaining rollout work](paper-order-engine.md)
- [Persistent acceptance summary](evidence/2026-11-12-paper-engine-v4.json)
- [Six existing skill candidates and review depth](skill-catalogue-review-2026-11-12.md)

Broker trials exposed sibling-cancellation acknowledgement handling and the normal conditional `held` stop state. Both were corrected and covered by regressions. Earlier blocked, unfilled and recovery attempts remain recorded.

**Still outstanding:** persistent hosting, trusted scanner-intent ingestion, Lovable order-status display, operational alerts, actual fees/corrections and eventual Trading 212-specific demo acceptance. The host template and read-only JSON status report are available. Live orders and scanner auto-execution remain disabled.

Ordinary verification runs are now broker-read-only. Further order exercises require an explicit manual workflow selection and a new exercise ID. These engineering checks made no paid AI calls. No additional third-party skill was installed by the catalogue scan.
