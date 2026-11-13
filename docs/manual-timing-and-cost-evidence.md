# Manual timing and private cost evidence

This adds evidence collection and an entry-feasibility audit around the confirmed EUR1,000 / EUR50 daily-loss / 1–5 minute test profile. It does not change strategy selection, execution limits or existing portfolio histories.

## Observed alert clock

For a current stock paper-watch notification, record the Telegram request start, confirmed response acknowledgement, optional provider message date, decision identity and plan hash in a separate signed append-only research partition. No chat ID, message ID, credentials or message text is included. Ordinary notifications retain their existing one-attempt ledger. A research-recording failure never resends the message or reruns paid review.

Telegram acknowledgement is **not a device delivery or human read receipt**. The response scenarios explicitly assume the user acts 60, 180 or 300 seconds after that acknowledgement. Durable decision/clock receipt can delay readiness further. The original offline test profile remains frozen; the new adapter declares this observable proxy instead of relabelling it as measured user behaviour.

Protocol: `b36797c142938dd01cca74855ab641dd51de6d5889d70aba2b780c2725c7cf8c`. Prospective evaluation starts **16 November 2026**. Earlier alerts are not retrospectively assigned a receipt time.

## Timing audit

Read clocks first. If none exist, do not fetch the full quote journal and do not infer zero approved reviews from unread data. Otherwise reconstruct that day's original guarded comparison through its existing identity/receipt validator and bind each clock to the exact reviewed packet, decision and plan.

For each declared delay, retain the original expiry and exit buffer. Count only a fresh reference quote after readiness, within the recorded plan window, meeting the existing 20bps spread and entry-gap checks and the breakout price. A supported stop crossing after the acknowledgement invalidates the setup, even if price later recovers.

The report distinguishes eligible reference quotes, invalidation, expiry before response, waiting, missing source review and no observed qualifying quote. Missing observations do not prove that an opportunity never existed. The session assumption is the approved plan's window, not a new live exchange or halt check.

This is **timing and price feasibility only**. It does not create paper fills, evaluate a shared EUR1,000 portfolio, implement the EUR50 daily halt, measure P/L or verify total broker costs. The earlier 41 risk/timing boundary checks remain the starting point for that separate portfolio integration.

## Private fee/FX evidence

The existing read-only Invest collector now retains `initiatedFrom`, `walletImpact.fxRate` and each itemized fee's name, currency, amount and charge time. It preserves absent fees as null and an explicit empty list as empty. Net cash and realised P/L are not recalculated or overwritten. All records remain in the owner-bound private account snapshot, under the existing signed ingestion and access controls.

A private arithmetic diagnostic compares reported net cash with gross native value, itemized EUR fees and each possible FX orientation using a declared EUR0.02 tolerance. The live read-only import established that fee entries are signed negative deductions and `netValue` is a positive magnitude for both buys and sells in the observed records. The diagnostic derives cash direction from order side while preserving every stored value. A signed negative BUY net value is also accepted. Positive fee entries, mixed signs, a negative SELL net value or foreign-currency fees remain unsupported and retained. Outcomes are matched, ambiguous, unreconciled, incomplete, unsupported or non-trade. Both FX directions matching remains ambiguous.

Matching cash arithmetic does **not** establish the broker's full fee formula, spread, slippage or complete round-trip cost. Existing cost scenarios remain assumptions. The diagnostic is intended to identify usable records and unresolved semantics before calibration.

Sources reviewed: [Trading 212 historical order schema](https://docs.trading212.com/api/historical-events/orders_1) and [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage). Provider documentation supplies field definitions; the reconciliation tolerance, delay scenarios and comparison method are our engineering choices.

## Validation and rollout

The runtime is built from the exact current collector/reviewer source `208f4bf5f9f1f403fb977075f0ea33912f4463b0`, adding only the relevant files. The previous research branch's unrelated strategy changes are not promoted. The private importer and its immediate dependencies matched the deployed account source before the change.

Initial local and hosted full suite: **1,669 passed**. The subsequent fee-sign correction adds positive net-value BUY, signed deduction, negative SELL and mixed-sign boundary checks. Targeted checks also cover null versus empty fees, currency/FX ambiguity, unchanged stored net cash, original expiry, fresh post-response quotes, stop invalidation, source binding, missing clocks and no notification retry after a recording failure. Final verification and rollout receipts are recorded in the main handoff.

Deployment order: validate/publish the backward-compatible dashboard contracts; verify a private read-only account import and a separately signed manual report; then update only the account/reviewer pins and add the isolated no-model audit job. Keep the original collector and other research workers pinned.

No new API subscription, AI budget increase or live order operation is introduced.
