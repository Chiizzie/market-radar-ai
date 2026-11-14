# Manual execution test profile — 13 November 2026

Status: **frozen profile and offline risk checks complete; timing checks are now connected to a separate prospective audit. Shared-capital portfolio and daily-halt integration remain outstanding.**

Current rollout: [manual timing and private fee evidence](manual-timing-and-cost-evidence.md), [verification receipt](evidence/manual-evidence-deployment-20261113.json). The timing adapter explicitly assumes response 60/180/300 seconds after Telegram server acknowledgement; it does not claim a human read receipt.

Charlie supplied these inputs: EUR1,000 paper capital, EUR50 maximum daily loss, available throughout the trading day, and a response to alerts within 1–5 minutes.

| Setting | Frozen test value | Origin |
| --- | --- | --- |
| Initial paper balance | EUR1,000 | User |
| Daily loss ceiling | EUR50 | User |
| Availability | All existing permitted trading hours | User; existing market/session restrictions retained |
| Response scenarios | 60, 180 and 300 seconds | Sample points within the user's 1–5 minute range |
| Primary scenario | 300 seconds | Conservative engineering choice, not an inferred typical delay |
| Per-trade planned risk | At most EUR20 | Existing agreed limit |
| Combined reserved/open risk | At most EUR40 | Existing simulator constraint, retained |
| Maximum allocation / concurrent reservations | EUR500 per setup / three | Existing simulator constraints, retained |
| Product | Trading 212 Invest | Existing initial scope |
| Entry cutoff | Before 22:00 Europe/Dublin and before any earlier session/setup deadline | Existing rule |
| Position horizon | Intraday; weekdays only | Existing rules |

The [machine-readable profile](../config/research/manual-execution-20261113.json) is bound to content ID `31cb0c3f4bbcd52fe1c4cf62b4b72fc9113d1ef1368befb4b141c9d00b488b5b`. Modified parameters require a new deliberate binding; recomputing the file's own hash is insufficient.

## How the daily limit is interpreted

For new admissions, the offline check requires:

`max(0, -today_net_realized_pnl) + existing_reserved_risk + proposed_risk <= EUR50`

The daily clock is Europe/Dublin. The net loss is measured from that day's starting balance. Existing risk includes pending, open and unresolved positions and must include the declared cost assumptions. Profits do not increase either the EUR50 budget or the inherited EUR40 open-risk ceiling.

After EUR40 net realised loss, at most EUR10 of additional planned risk remains if none is already reserved. With EUR20 realised loss and EUR20 reserved, a proposed EUR15 risk is blocked. An observed net loss of EUR50 must latch a halt on new admissions for the rest of the day, including if a later close improves net P/L.

These are limits on admission and planned exposure, not a guarantee that gaps or unknown fills cannot exceed them. The new helper consumes a supplied halt latch; a future replay integration must persist it and reconcile the daily ledger. It does not implement a new account ledger or manage exits.

## What the delay checks do

Readiness is the later of actual alert receipt plus the declared delay, and decision availability. Quotes must have been observed after readiness, received by the evaluation time and remain fresh. Existing setup expiry and the inherited 30-second exit buffer are preserved.

A four-minute setup can pass the timing checks at one or three minutes, but fails at five. A setup expiring exactly at the response time also fails. The helper never extends an expiry or substitutes assembly time for a missing alert receipt. Missing delivery, quote, session or risk evidence remains unknown.

All-day availability does not change session permissions, the Dublin cutoff or weekend restrictions. Each delay scenario is an alternative; their returns must never be added into one account.

## Implementation and checks

New module: `agents/manual_execution_profile.py`. It provides strict profile validation and separate risk/timing checks. Its only passing status is `profile_checks_passed`; every response retains `trade_authorized: false`.

These are additional offline checks. They do not create fills, issue orders, resize a trade, widen a stop or replace eligibility, spread, price-gap, duplicate-symbol, session or exit policies. No network/model/broker code or new dependency was introduced.

**41 targeted tests passed** using synthetic cases. They cover daily loss plus reserved risk, available cash, per-trade and combined limits, retained overnight uncertainty, missing costs, a persisted halt, each delay, exact expiry, stale/future quotes, missing alert receipts, late decisions, Dublin summer time, weekends and profile tampering. At that initial profile-only milestone, production modules and workflows were unchanged. Subsequent timing/cost integration has separate full-suite and deployment receipts linked above; no broker-paper performance result is claimed.

Reproduce from the source revision recorded in the handoff:

```sh
python -m pytest -q tests/test_manual_execution_profile.py
```

The [offline receipt](evidence/manual-execution-profile-20261113.json) records hashes and illustrative gate results. All illustrated cases are synthetic, not market results.

## Next measurable milestone

The separate timing audit now records acknowledgement-based scenarios; private fee/FX retention and cash arithmetic have been commissioned. Next, connect the profile to a separate shared-capital replay, retaining old portfolios, persisting the daily halt and reserving unresolved exposure. Collect later-day clocks and quotes before reporting usable-entry rates. Reconcile full cost assumptions separately: observed fee arithmetic alone does not measure spread or slippage.

No further input from Charlie is needed for those engineering steps. The initial settings and boundary checks are complete; integration and forward performance evidence remain outstanding.
