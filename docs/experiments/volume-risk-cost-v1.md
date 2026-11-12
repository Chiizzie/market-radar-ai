# Volume, risk and cost experiment

Prepared 12 November 2026, Europe/Dublin. **Approved, but not activated.** The
user approved the Lovable plan and integration/activation on 12 November. The
plan approval was accepted at approximately 16:52 Dublin. Lovable committed a
partial dashboard implementation, then refused the required follow-up because
the workspace is out of credits. That partial change is not ready to publish.
The ordinary scanner remains at runtime 3a113a4. Dashboard publication and a
complete natural run are required before claiming prospective collection began.
See [the saved integration review](volume-risk-cost-dashboard-review.md).

## Hypothesis and scope

The 11 November baseline had 12 losses in 13 closed reference-price simulations,
and a median stop distance of 0.4372% against a blanket 0.40% cost assumption.
Later intraday volume compared with the opening surge can reject continuing
strength. These observations motivate tests; they do not establish that a change
will improve profits. This is a new deterministic continuation experiment, not
the exact production AI strategy or a retrospective rewrite of its results.

Freeze [the protocol](volume-risk-cost-v1.json) at
`c796287f67ef1be3a30d2dcdb1cdea8183e8ec75eb34a5bc9885b480ad2059b1`.
12 November is development/commissioning. Prospective full-session validation is
planned from 13 November, **only after activation**. Retain late-start, interrupted
and missing-data sessions. Never label periods before actual activation as tested.

All captured stocks enter the same screen. Common eligibility needs twenty
contiguous completed five-minute regular-session bars, positive momentum, price
above rolling VWAP, a current bounded news check, an identifiable US Invest
catalogue candidate, fresh IEX quotes/FX and an unpassed trigger. This tests
continuation from 100 minutes after the open; the existing 30-minute opening
strategy is outside this experiment. Catalogue identity is not account permission.

The first common eligible setup per symbol/day is frozen once across all ten
variants, including variants that fail. A later capture cannot rescue a rejected
variant, restart expiry or retry a losing setup. The active observer capacity is
40 unique symbols. Capacity and source deferrals are explicit. Each admitted
variant is an independent hypothetical allocation, not one shared portfolio.

## Fixed comparisons

The 2×2×2 matrix contains eight variants:

| Dimension | Control | Alternative |
| --- | --- | --- |
| Volume | Mean of last 5 bars / mean of previous 15; minimum 1 | Same last 25-minute NY window / prior-session mean; minimum 1 |
| Stop/target | Last 3-bar low; target for net 2R including worst allowed entry gap/costs | Stop at the lower of structural stop or entry minus 1.5 ATR14; target capped by 3R gross, 6 ATR14 and observed overhead resistance |
| Cost | Legacy extra 40bps assumption | Existing USD balance, assumed 5bps adverse slippage each side, applicable US sale-levy allowance |

Two further sensitivity variants use same-time volume and ATR risk with
EUR conversion on both legs (15bps each) and stressed slippage (20bps each).
No parameters are selected after seeing validation outcomes.

Volume uses the existing split-adjusted historical context cache: up to ten prior
full sessions and at least five complete samples for the identical five buckets.
Missing bars are unknown, never zero; current/future sessions, early closes,
duplicate dates, altered hashes and future/stale receipts cannot supply history.
NY local time handles DST. IEX volume is partial-venue volume, not consolidated
volume. This does not improve the underlying feed's missing-symbol coverage.

ATR14 is the arithmetic mean of fourteen completed five-minute true ranges.
Stop width is capped at 3%. Net estimated reward must remain at least 2R after
costs; an ATR projection with insufficient room is rejected. Targets remain
projections, not guaranteed support/resistance. Quantity decreases to keep
planned loss ≤EUR20 and reserved capital ≤EUR500, including the maximum 20bps
entry gap. These planned limits cannot cap gap losses.

## Costs, observations and unknowns

Fees checked against Trading 212 primary documentation on 12 November. FX is
0.15% for each conversion; USD-balance scenarios exclude prior funding and later
withdrawal conversions. Conditional US sale allowances use 0.00206% of sale
value and USD0.000195 per share. Each fee component rounds up to a euro cent as
an explicit conservative assumption. Fee admissions expire 12 December 2026.
Commission is assumed zero for Invest. ADR charges, instrument-specific taxes,
the actual account route and broker fills/rounding remain unverified. Slippage
is an assumption, not an observed fee. CFD and crypto costs are out of scope.

Entry uses observed ask plus assumed slippage; exit uses observed bid minus
slippage. Spread is already embedded and is not subtracted again in the
itemised cost profiles. The legacy flat40 variant intentionally retains its
extra blanket cost assumption. Native USD observations are retained and
converted at the cohort's fixed indicative FX rate; subsequent FX P/L is not
modelled. No AI is called or cost attributed to this experiment.

Admission and fills use the latest local/database receipt time, never a
backdated exchange timestamp. No same-observation entry and exit. Quotes over
20bps wide cannot fill or invalidate a pending setup. A wide quote suggesting
an exit leaves the trade unresolved; a later favorable quote cannot replace it.
No observed exit by the deadline remains unresolved, including a quote arriving
one second late. No synthetic prices or intrapoll highs/lows are fabricated.

## Evaluation and recovery

Signed append-only enrolments include exact sources and all variant plans.
Restoration checks event identity, partition, sequence and deterministic source
recomputation. A disposable projection cannot create missing events. Failed
storage writes do not count as observations. The observer runs every five
seconds in bounded 330-second jobs, overlapping the usual five-minute dispatches.

Reports retain blocked, watching, open, unfilled, unresolved and closed states,
cost-adjusted net results, costs, closed-only drawdown and quote gaps separately
for every variant. No closed trades means null/not established, not break-even.
`paired-results.json` compares only matched closed symbol cohorts and states the
excluded count; this subset may be selection-biased. Full-arm states remain in
`report.json`. Symbols within one day are correlated: evaluate across later
days/regimes, including interrupted sessions. No trade count alone proves an edge.
No automatic promotion into alerts or orders is implemented.

Full source events, reports, health and paired comparisons are retained as
30-day GitHub artifacts. The append-only database is authoritative. Restore is
bounded to 75MB/100,000 source events and 90 seconds per sync; capacity errors
fail the experiment explicitly. Review the restore time and archive retention
before this boundary becomes material. Production restore/download has not yet
been demonstrated for this new protocol.

## Activation checklist

1. Review/pass the producer regression workflow and synthetic contract fixtures.
2. Restore Lovable editing capacity; approval has already been supplied. Fix the
   recorded producer/parser mismatches, validate every actual producer fixture,
   finish migration/build/auth checks and publish dashboard support. The additive
   database constraints and viewer policy are present, but that alone does not
   make the unpublished HTTP validator usable.
3. Add [the prepared job](../../deploy/strategy-experiment-job.yml) with its exact
   tested runtime SHA and enable only `STRATEGY_EXPERIMENT_ENABLED`. Existing
   collection/review/watcher pins, budgets and order settings remain unchanged.
4. Inspect a full natural run, durable source/report receipts and viewer output.
   Record actual activation time; do not count earlier captures as forward trades.

## Verification checkpoint, 12 November 2026

- Producer commit `73d880261768b32453986d7da717058810178920`: 155 focused
  regression tests passed locally and in [CI run 43259903724](https://github.com/Chiizzie/market-radar-ai/actions/runs/43259903724),
  including 30 experiment tests. Runtime source is unchanged at this checkpoint.
- Dashboard commit `7b59aab79e14c59aee3574df9d060d20dba49458`: provider reports
  unfinished build verification. Independent offline testing of the committed
  validator accepts empty report and screen fixtures, rejects enrolment because
  the cohort safety fields are absent from the schema, and rejects watching and
  closed reports because reserved capital is incorrectly treated as notional.
- Database inspection confirms the new kinds/protocol constraint and restricted
  report-only viewer policy. There are zero records for the new protocol. No
  synthetic fixture was ingested, no new worker was enabled, no publication was
  attempted, and production workflow pins/budgets were not changed.
- Ordinary [16:50 collection run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43262983134)
  completed all seven jobs successfully. The separate
  [16:52 health run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43263449903)
  failed with `comparison_storage_unavailable`; the subsequent
  [16:58 health run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43264367635)
  passed and database receipts continued through 16:59. The transient's cause
  is not established; this checkpoint does not claim continuous availability.

Primary sources:
- https://docs.alpaca.markets/us/reference/stockbars
- https://docs.alpaca.markets/us/docs/market-data-faq
- https://www.trading212.com/terms/invest
- https://helpcentre.trading212.com/hc/en-us/articles/360007081637-What-are-the-applicable-stock-exchange-fees
- https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account
