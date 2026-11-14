# Manual shared-account paper simulation

Implemented 14 November 2026. Prospective evidence starts **16 November 2026**.

## Purpose and frozen comparison

The preceding timing audit could identify a usable reference quote but could not determine whether simultaneous trades fit Charlie's account. This separate engine tests that missing constraint: EUR1,000 shared starting capital, EUR50 daily loss budget, manual response at 60/180/300 seconds, and the existing risk and expiry rules. It does not change the live scanner's selector, alerts, paid reviews or existing portfolios.

Nine accounts are alternatives: three response delays times three existing cost assumptions (EUR conversion, existing USD balance and stressed slippage). Each starts with EUR1,000 and carries its own closed result across days. Never add their balances or P/L. The primary scenario is EUR conversion with a 300-second response. This is a conservative benchmark, not an estimated response distribution or a guarantee of broker execution.

Profile: `31cb0c3f4bbcd52fe1c4cf62b4b72fc9113d1ef1368befb4b141c9d00b488b5b`.
Portfolio protocol: `2080e2e70d7380759e1269d0b5603d6533d4e7ddc079cd354451182dc135a13f`.
The [complete protocol](manual-portfolio-protocol.json) binds the existing guarded comparison and separate acknowledgement-clock partition. No historical alert receives an invented receipt clock.

## Account and loss accounting

- A notified, approved USD-stock plan reserves cash and planned stop risk when both its review and acknowledgement evidence become durably available. The manual delay starts at Telegram acknowledgement; it is not measured human receipt.
- Source quantity may only decrease to respect EUR500 maximum allocation and EUR20 risk including the declared cost scenario. Stops and targets are preserved. All active reservations share the account; there are at most three, at most EUR40 combined planned risk, and no concurrent duplicate symbol.
- The additional daily check requires `max(0,-today_net_realized_pnl) + other_reserved_risk + proposed_risk <= EUR50`. Existing reservations include pending, open and unresolved exposures. Cash, risk and timing are checked again at entry. A denied setup is not retried after observing later prices.
- Once net realised trading loss reaches EUR50, the daily halt is latched and unfilled reservations are cancelled. Later profitable exits do not clear it. Existing open positions still follow their exit rules. Only the next Europe/Dublin calendar date resets that day's latch; the balance and unresolved exposure carry forward.
- Balances reflect closed trading P/L. Pending/open cash and conservative cost allowances stay reserved. There is no mark-to-market equity estimate, and no closed P/L is reported until an exit is observed. Paid AI costs are separate and excluded from these trading balances.

The daily ceiling is an admission rule and planned exposure budget. A fast gap can produce a larger realised loss. It is not a guaranteed loss cap or a stop installed on Charlie's broker account.

## Timing, quotes and unresolved exposure

Readiness is the latest of acknowledgement plus the chosen delay, durable acknowledgement availability and durable reviewed-plan availability. Quotes observed before readiness cannot fill, even if received later. Keep the original setup expiry, intraday exit deadline, 30-second exit buffer, weekday restrictions and Dublin 22:00 entry cutoff. A five-minute response can therefore miss a shorter-lived signal; the simulator does not extend the plan.

The first qualifying reference ask, plus assumed slippage, supplies a hypothetical entry. Spread and entry chase are capped at 20bps and quote age at 60 seconds. Net reward must remain at least 2R after the cost scenario. A supported stop crossing after acknowledgement invalidates the unfilled setup, including when the clock record reaches storage after that quote. Repeated exchange observations cannot provide both entry and exit.

Exits use a supported bid minus slippage at stop, target or in the final 30 seconds before cutoff. A late quote cannot invent an on-time exit. A wide quote at an exit boundary or an open-position observation gap over 60 seconds makes the position unresolved. Its cash and risk remain reserved indefinitely, pending reservations are cancelled, and all new entries are blocked. No later favourable quote repairs the unknown path. Resolving such exposure requires a separately designed evidence/reconciliation policy; it is not silently written off.

This is a new, deliberately conservative quote-gap policy in its own experiment. Existing historical portfolio results remain untouched. Session permission comes from the approved source plan, not a new exchange/halt probe. The cohort contains only approved, notified USD-stock plans with recorded clocks; missing clocks and upstream rejections are not additional tradable observations. Broker liquidity, partial fills, queue position and sector correlation remain unmodelled.

## Cost assumptions

The original cost functions are reused without changing their historical series. EUR conversion is 15bps per leg, with 5bps adverse slippage per side. The USD-balance alternative omits trade-time conversion but not prior/later funding conversions. Stress uses 20bps slippage per side. The existing US-sale levy allowance and rounding up each fee component to a euro cent are retained. Bid/ask spread is already embedded in the simulated prices and is not charged twice. EUR conversions retain the source plan's FX assumption rather than inventing a later FX history.

The published [exchange-fee schedule](https://helpcentre.trading212.com/hc/en-us/articles/360007081637-What-are-the-applicable-stock-exchange-fees) and [multi-currency description](https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account) were rechecked on 14 November. Actual fee/FX records are captured by the separate private account importer; they are not exposed to this public research worker or automatically used to tune scenarios. Applicable taxes, ADR fees, FX route, spread and slippage are not fully verified. Cost admissions retain the original expiry of **8 December 2026**. Review and version assumptions before that date; do not silently extend them.

## Persistence and recovery

Signed, append-only PostgreSQL source events are authoritative. Each run reconstructs all clock-bearing days since 16 November in durable sequence order, using the later of occurrence, database receipt and prior replay time. The evaluation watermark is fixed before remote reads. The report distinguishes that evidence cutoff from its later generation timestamp. This avoids treating a newly generated report as new market evidence.

The daily halt, account balances, reservations and transitions are rebuilt from the retained history, not reset when a process starts. A local SQLite spool bounds memory. Complete sources and the full nine-account ledger are exported as compressed artifacts; re-reading both must reproduce the exact report, ledger and hashes before publication. Remote signed-source corruption, read failure or the declared 366-day / 1GB / one-million-event capacity bounds fail the run. No partial account result is published as complete.

Reports retain all counts and balances while showing the latest eight setups and ten daily summaries per account; omitted counts and the full-state hash are explicit. Full ledgers accompany each run. Workflow artifacts expire after 30 days; source events remain authoritative. Backups and signed source storage are still dependencies, not a promise of unlimited retention or uninterrupted service.

## Operation and validation

The separate `Manual shared paper portfolio` workflow runs approximately every 15 minutes on weekdays within 08:00–23:00 Europe/Dublin. Explicit commissioning can run outside that window; prospective admission still starts on 16 November. CI scheduling can be delayed. This is retrospective paper replay, not a continuously hosted order-management service. Only the signed research secret is supplied; no model, broker or Telegram credentials are available to the worker.

The Performance page adds **Your manual paper simulation**, using existing authenticated viewer access. It shows alternative balances, reserved/available cash, daily halts and unresolved exposure. Signing out clears protected cached data, including outstanding requests. Existing research panels and trade gates stay separate.

Thirty focused Python tests cover shared capital, reservation/position limits, daily and open risk, delay/expiry, retained pre-entry invalidation, daily halt despite later profits, Dublin rollover, missing evidence, observation gaps, late exits, exact source binding, duplicate/restart recovery, disk failure, a 200-alert capacity rehearsal, and the complete guarded review-to-clock-to-portfolio path. Frontend tests cover the producer contract, arithmetic/timing tampering, separate signed ingestion, result display and sign-out races.

Run the focused checks with `python -m pytest -q tests/test_manual_portfolio.py`; the JSON fixture is explicitly synthetic. Final hosted, deployment and storage receipts belong in `docs/CONTINUE-HERE.md` and the deployment receipt. Engineering checks do not establish profitability. Later unseen sessions are still needed to assess usable entries, costs, unresolved rates and outcomes.
