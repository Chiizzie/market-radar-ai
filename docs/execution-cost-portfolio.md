# Cost scenarios, shared paper portfolios and session readiness

Implemented 8 November 2026. The original scanner, existing code/AI protocol,
AVWAP protocol, paid budgets, alerts and qualification rules remain unchanged.
No orders or additional AI calls are introduced.

## Scope and what this can establish

This is a separate deterministic sensitivity experiment using the immutable
prospective code/AI comparison events from 8 November onward. It is **restricted
to the existing code-qualified cohort**. Candidates rejected by the original
40bps gate never entered that cohort and cannot be recovered here. Consequently
this experiment can compare costs and capital constraints on shared candidates,
but cannot measure the opportunity set of a cheaper-cost discovery strategy.
An expanded eligibility experiment needs its own prospective enrolment and quotes.
Existing AI approvals are reused; reviewers have not assessed the new scenarios.

The six portfolios are alternatives (three cost profiles by code-only/AI-approved).
Each starts with fictional EUR1000, carries its balance across days, permits at
most EUR500 per setup and three simultaneous reservations, EUR20 planned risk
per trade and EUR40 combined planned risk. This is not the user's account balance.
No leverage, account permissions, sector classification or correlation is inferred.

## Costs and execution assumptions

Primary sources checked 8 November 2026:
- https://www.trading212.com/terms/invest
- https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account
- https://helpcentre.trading212.com/hc/en-us/articles/360007081637-What-are-the-applicable-stock-exchange-fees

US-dollar stock scenarios only:
1. EUR conversion on entry and exit: 15bps each leg, 5bps adverse slippage each side.
2. Existing USD balance: no trade-time FX fee, 5bps adverse slippage each side.
3. Stressed EUR conversion: 15bps each leg, 20bps adverse slippage each side.

Commission is assumed zero under the cited Invest schedule. US sale levies use
the published 0.00206% sale value plus USD0.000195 per share as an allowance.
Each fee component is rounded up to a euro cent as an explicit conservative
modelling choice, not verified broker rounding. Actual account currency route,
instrument-specific tax/levy applicability and ADR charges are unverified.
No-conversion excludes earlier funding and later withdrawal conversions.
Crypto and non-USD stock fees are unavailable, not free.

Buy at observed reference ask plus assumed slippage; sell at bid minus slippage.
The bid/ask spread is already embedded and is never also subtracted as a fee.
Quote sources are reference venues, not executable Trading 212 quotes.
EUR quote conversion and the USD levy conversion retain the source plan's FX
assumption; subsequent currency movements are not modelled. Fee snapshots expire
8 December 2026; new admissions fail closed thereafter until a new version.

## Deterministic capital and chronology

Source events are validated by the existing immutable comparison validator,
then processed in durable sequence order. Effective availability is the latest
of source receipt, durable database receipt and prior processed time. An AI arm
cannot backdate eligibility to an approval received later. Exchange observations
before admission, future quotes and quotes over 60 seconds old cannot fill.

Pending setups reserve capital and initial stop risk before entry. Quantity
can only decrease from the source allocation; entry, stop and target structure
are preserved. Reservation sizing includes a 20bps entry gap, adverse slippage,
exit fees and rounded FX costs. Net reward must remain at least 2R. An actual
entry is rechecked against the reservation; spread and entry gap must each be
at most 20bps. No same-observation entry and exit is allowed. Simultaneous events
use durable receipt order rather than selecting retrospectively by outcome.

Denied candidates are not retried after seeing later prices. Duplicate symbols
cannot take simultaneous allocations in one portfolio. Expired or invalidated
pending setups release their reservation. Observed exits release reservations
and add net P/L to the balance. Exits use the first observed stop, target or
quote in the 30 seconds before the mandatory cutoff. No late quote fabricates
an on-time exit. Unresolved open positions retain capital and risk across days;
they never silently become closed or free cash. Gaps may exceed planned loss.

Reports include all portfolio totals and the latest 20 detailed setups per
portfolio, with omitted counts. Closed P/L is null until a close is observed;
unrealized equity is not estimated. Paid review costs remain separately labelled,
including unreconciled costs. Initial balances are not profits. Baseline and AI
allocations are alternatives and must not be added together.

## Deployment and recovery

The independent execution-research workflow follows completed scanner runs and
has morning/pre-open UTC candidates selected using Dublin/New York timezone
checks. GitHub scheduling can be delayed; it is not guaranteed continuous hosting.
Explicit push/manual verification may run outside the weekday window. Existing
scanner jobs and source pins are not changed. No model/order/Telegram credentials
are supplied; only a boolean indicates whether the configured AI key is present.

Durable reports use strict signed schemas and viewer-only RLS. Raw source events
remain private through the dashboard API. Each run reconstructs up to 366 days
and 50MB of evidence, fails closed at capacity, and exports a compressed lossless
source archive, retained 30 days. Local archive readback and independent replay
must exactly reproduce the report before publication. This does not prove later
artifact-download availability. The database remains the source of truth.

Readiness checks separate configuration from evidence: budget headroom includes
unsettled reservations and lifetime caps; key presence is not OpenAI credit.
Alpaca clock and one SPY quote are read-only probes, not broad market coverage.
Actual dispatch and completed job metadata are inspected. No populated cohort
means sustained watcher capacity remains unproved. Recovery-upload receipts are
checked against each family's cutoff, with the first natural backup due Monday.
No readiness state authorizes a trade or establishes profitability.
