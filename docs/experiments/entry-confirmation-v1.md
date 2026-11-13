# Paired entry confirmation — frozen 13 November 2026

Hypothesis: requiring the bid to reach the existing trigger may reduce entries
caused only by the ask crossing, but may miss winners or pay more for later fills.
This is prospective paper research, with no profitability or broker-fill claim.

Development evidence: replay of 12,562 events in artifact 14067983384 from run
43488085070 reproduced all ten existing variant totals. All five closed USD
structural examples entered while bid was below trigger; four never subsequently
recorded a bid at trigger before stopping. These five outcomes motivate the test;
they are not independent validation and are not relabelled as avoided losses.

Frozen protocol: c73bb1ce0fe2f7e1db2cfa27d4fafdad8d65f31de1e12ff5514cc647d5dc27dc.
Source protocol: c796287f67ef1be3a30d2dcdb1cdea8183e8ec75eb34a5bc9885b480ad2059b1.
Source implementation: fc12be18156a2ebbef2141275bf07f3962655e71.
Both arms reuse the rolling_structural_usd plan builder and its complete cost,
risk, spread, sizing, gap, expiry and exit rules. Only the extra bid >= trigger
entry condition differs. USD prices, EUR accounting, five basis points assumed
slippage per side and existing conditional USD fee model. Spread is represented
once, through ask-entry/bid-exit. The original experiment and its records continue.

First common eligible capture per symbol per session, maximum 40 active symbols
and 500 total cohorts per day. Common-source failures are screened out; variant
blocks remain counted in both arms. No catch-up or revising frozen setups. Durable
receipt time prevents backdated entries. Independent IEX quote polling continues
while either arm is watching/open, even after the other terminates. Windows use
New York exchange time with weekday checks; shared session clock retains the
existing intraday exit deadline. No new model calls, notifications or orders.

13 November is commissioning/development; validation sampling begins 16 November.
Do not tune this policy during validation. Report every arm's full state counts,
closed P/L, fees and slippage separately. These are independent allocations, not a
portfolio. Do not compare alternative arms by summing their account results.

Paired delta is bid-confirmed minus ask-trigger net EUR only where BOTH close and
usable quotes have no receipt gap above 15 seconds from first entry through last
exit. Quotes must be fresh at durable receipt and have spread <=20 bps. Report
excluded counts; this matched-closed subset can itself be biased. Unfilled,
open and unresolved outcomes are never zero returns. Also compare participation,
unresolved rates and per-session closed results; a small favourable subset alone
cannot promote a strategy. Inspect multiple later sessions/regimes and uncertainty
before choosing whether to change production. Retain source events for replay.

Private dashboard reports show each side's bid/ask/fill, spread, source age, and
initial fill-to-bid shortfall as a percentage of fill-to-stop distance. They show
latest screen blockers separately from outcomes. Signed machine ingestion accepts
only this frozen partition; viewers can read reports, never raw enrolment/quotes.
No data subscription, budget or live trading setting changes are included.

Validation: synthetic quote/durability/coverage tests plus existing scanner suite.
The older source branch lacks main's scheduled workflow: CI reads its exact
86524f8 deployment snapshot for boundary checks. The pre-existing lifetime budget
test fixture is updated from EUR4.90 to EUR99.90 reserved, reflecting the already
configured EUR100 limit; no runtime budget change is made.
