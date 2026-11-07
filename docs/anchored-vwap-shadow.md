# Session-open AVWAP shadow experiment — 7 November 2026

This is our own fixed intraday adaptation of published anchored-VWAP and
multiple-timeframe concepts, described at https://alphatrends.net/ and
https://alphatrends.net/anchored-vwap-book/. It is not a replication of private
trader calls or evidence of independently verified returns. The session-open
anchor makes this particular AVWAP an ordinary regular-session VWAP approximation.

## Fixed protocol

`session_open_avwap_reclaim_v1`, hashed together with all rules into its own
experiment ID. Rule changes require a new protocol and must not rewrite old
results. The main code-versus-AI comparison and original scanner are separate.

- Stocks only, long only, drawn from the current captured set (at most 40).
  This does not add whole-universe coverage or crypto trading methods.
- Anchor exactly 09:30 America/New_York. Fetch the full session independently
  of the existing 60-bar capture. Require 18 completed contiguous five-minute
  bars (90 minutes); missing opening bars, gaps or unfinished bars block.
- HLC3 times IEX volume is a bar approximation on a partial exchange feed.
  Completed fifteen-minute buckets: EMA3 above rising EMA6, last close above
  EMA6. Prior daily close above rising SMA5, using at least six prior sessions.
- Fresh bullish close back above rising AVWAP after the prior close was at or
  below it; maximum 100bps extension. Last three bars' mean volume at least
  1.25 times the preceding fifteen, not a same-time historical-volume statistic.
  At least USD1m observed session notional.
- Current market clock, indicative EUR conversion, uncrossed IEX quote with
  spread at most 20bps, and exactly one Invest catalogue candidate. This does
  not assert account permission, executable prices or instrument halt status.
- Entry trigger: reclaim bar high plus 10bps, still above current ask. Stop:
  lowest of last three lows less 0.1 ATR14. Width at least max(20bps,0.5 ATR),
  at most 300bps. Net 2R target must fit below observed prior intraday peak
  and previous daily high when overhead; no invented target to pass a gate.
- Independent fictional EUR500 allocations; maximum planned loss EUR20,
  including fixed 40bps round-trip costs. This is not a portfolio return;
  observed gaps can produce a larger realized loss than planned.
- Fresh successful bounded publisher news query required, positive catalyst
  not required. No AI or human assessment of headline meaning. Missing news,
  corporate actions, earnings/event calendar and halt knowledge remain limits.
- At most one qualifying enrolment per stock/session, first database sequence
  wins. Quotes must be received after durable enrolment and before the original
  60-second expiry. Entry spread and trigger gap capped at 20bps; exit quotes
  are never suppressed by an entry spread filter.
- Scheduled exit starts 30 seconds before market close minus five minutes, or
  22:00 Dublin if earlier. Late quotes cannot invent an on-time exit. Missing
  closing evidence remains unresolved, with no assumed gain or flat result.

## Runtime and reporting

The independent `method-shadow` job uses existing five-minute dispatches, after
collection, from 09:30 through 16:15 New York on weekdays. There is no added
cron service or paid subscription. It observes every five seconds for 330
seconds; these GitHub workers may overlap or have scheduling gaps. Observed
poll gaps and data failures are reported. It is not guaranteed continuous or
streaming coverage. Failed collection falls back to observing existing setups.

No OpenAI, Telegram or budget credentials are passed to the job, and no order
or notification client is used. It never registers an approved paper trade.
Default enabled; set repository variable `METHOD_SHADOW_ENABLED=false` to pause
new workers. Existing immutable evidence remains intact.

Signed append-only `research_events` store `method_enrol`, `quote` and
`method_report` in the method's protocol partition. Migration 0007 adds a unique
first-enrolment index and preserves service-role insert/read-only privileges.
Viewer RLS exposes only reports, never raw scenarios or quotes. The disposable
projection verifies event digests and recomputes every enrolled scenario from
its frozen inputs. JSONL exports support independent recovery; compressed
end-of-session backups retain 30 days in Actions. Database remains authoritative.

`/performance` shows separate method counts, state breakdown, observed closed
net EUR results, latest screening reasons and observation health. Unknown
results stay unknown. A storage-only check records the true current cohort,
not a synthetic trade. A report with no screening explicitly says so.

## Acceptance and next evidence

Offline synthetic tests exercise the actual detector, risk/cost arithmetic,
missing anchors/gaps/future bars, daily trend, late receipts, entry spread/gap,
stop execution during a wide spread, immutable enrolment and event recovery.
Cross-language fixtures exercise the Python producer through the TypeScript
ingestion/parser. Synthetic fixtures are test-only and never production input.

The next evidence is prospective market sessions after rules are fixed. Review
coverage and complete outcomes before comparing net returns or considering an
AI-reviewed variant. Do not tune this method to the previously missed ASH trade,
count infrastructure tests as profitable trades, or promote it on a small streak.
See the deployment checkpoint on main for live deployment and verification IDs.
