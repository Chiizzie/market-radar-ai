# Discovery and chart-led paper milestone — 7 November 2026

The original `Chiizzie/market-radar` scanner remains operational and unchanged.
This change is confined to Market Radar AI. No orders, additional model budget,
automatic copying of original-scanner alerts, or paid development reviews are added.

## Why ASH was missed

The original [6 November 18:48 Dublin alert](https://github.com/Chiizzie/market-radar/actions/runs/42273559764)
ranked ASH 38th and recognised a trend pullback/reclaim. The AI captures at
18:45 and 18:50 included ASH in the 5,726-name catalogue pool but listed it as
`not_checked`, outside the 300-symbol preliminary history batch. The six reviewers
never assessed it. Individual IEX snapshot freshness/rank was not retained, so
the exact historical ranking cutoff cannot be reconstructed.

## Changes

- Broad IEX snapshots now rank relative session participation and recent price
  acceleration alongside capped liquidity and early daily movement, with an
  extension penalty. Activity lists and catalogue rotation remain independent
  inputs. The existing 300 preliminary / 40 detailed stock limits remain.
- Participation is explicitly **current daily-bar volume divided by the
  previous completed daily-bar volume**. This uses existing snapshot fields; it is not
  a multi-day average or historical same-time relative volume. Missing previous
  volume is unknown. No synthetic volume or price observations are created.
- Acceleration uses actual timestamps/prices from the preceding cached snapshot,
  only within the same New York date and a maximum 30-minute observation gap.
  First runs, unchanged timestamps, expired/corrupt caches and missing prices
  cannot claim acceleration. A separate versioned Actions cache preserves the
  original observation times. It contains public reference prices, no credentials.
- Each catalogue symbol has a retained selection trace: snapshot freshness,
  raw discovery measurements, ranking, priority/rotation lane, technical quality,
  detailed-selection status and reason. Active paper watches can displace a
  discovery selection; that is recorded explicitly. `discovery-selection.json`
  is a compact companion artifact; `discovery.json` and the run summary retain
  reconciled counts. Scheduled capture artifacts are retained for seven days.
- `trend_pullback_reclaim_v1` is a separate stock-only chart thesis: rising EMA
  trend, observed impulse, shallow pullback, EMA touch and completed reclaim.
  It requires at least 24 contiguous recent regular-session bars. The pending
  entry remains the pullback trigger plus 10 bps; a trigger already passed is
  not moved upward to manufacture another entry.
- This strategy retains positive momentum, recent volume >=1.5x, rolling VWAP,
  catalogue identity, fresh bid/ask and FX, expiry, session exit, EUR 20 planned
  risk, fictional EUR 500 allocation, assumed 40 bps round-trip costs, and 2R net
  reward. Targets are capped at observed session swing highs and half-impulse
  projection. Targets are never increased merely to satisfy the risk rule.
- The chart thesis does not require a fresh positive catalyst. It does require
  a current successful symbol-specific Alpaca news check, retained validated
  articles and zero rejected source items. Source outage, stale retrieval,
  unqueried symbols and global evidence-cap loss block it. News coverage remains
  explicitly bounded; all six independent reviewers can veto adverse evidence
  or a material gap. Momentum/opening strategies still require current news.
- The named strategy and chart evidence are preserved in qualification and review
  packets. Its label also appears in the existing plan trigger text, preserving
  the strict dashboard archive schema. Comparison reports group outcomes by
  strategy. The new comparison protocol requires a new database rather than
  mixing earlier strategy rules into an existing prospective cohort.

## Replay evidence and limits

`tests/fixtures/ash-2026-11-06-yahoo-replay.json` preserves the original session
bars, provider provenance, capture time and source run. These are Yahoo bars,
not reconstructed Alpaca/IEX observations. The original session has earlier
gaps; strict paper evidence tests use only its last 24 contiguous bars and never
fill gaps. The measured reclaim is USD 77.61000061035156, support is
77.1801986694336 and observed overhead cap is 79.5. The new chart detector
recognises this pattern. Its current rolling relative volume is 6.65136x.

The ASH replay still fails the new scanner's cost-inclusive 2R requirement at
that observed target. This is a transparent risk rejection, not an AI rejection
or evidence that the new strategy would have approved ASH. A separately labelled
fictional variant verifies qualification, all eight review stages, fresh
revalidation, watcher registration, observed simulated entry and closing. It is
software verification, not trading performance.

Snapshot ranking is tested with a constructed smaller stock whose relative
participation/acceleration outranks larger absolute-turnover names, then reaches
the bounded research batch. Missing/stale inputs, incomplete patterns, adverse
review vetoes, news failures and stop-crossing bids remain blocking.

## Next live evidence

Local verification: 1,223 backend tests passed, compilation and both existing
offline protocol scenarios passed, and the current dashboard's strict paper
archive parser accepted the new synthetic chart-strategy archive. The added
tests include a complete fictional entry/exit lifecycle. No model requests,
Telegram messages or provider orders were sent during these checks.

At the next regular session, verify fresh snapshot coverage, checkpoint reuse,
the new selection traces, and chart-strategy blockers. Compare original alerts
against their AI discovery trace without assuming a missed name should become
an approved trade. No new live entries or profit have been demonstrated by this
milestone. Partial IEX coverage and the bounded research queue remain limits.

Provider field reference: [Alpaca stock snapshots](https://docs.alpaca.markets/us/reference/stocksnapshots-1).
