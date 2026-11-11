# Post-deployment errors and paper outcomes — 11 November 2026

All times are Europe/Dublin (UTC on this date). This audit separates operational completion, reference-quote simulations, and actual broker executions. No broker order or user fill is inferred from a paper result.

## Findings

The accounting and dashboard repairs did not establish trading quality. The recent failed scheduled workflows inspected here failed in their quote watchers, while collection, account syncing, market context and review completed. Paid review later deferred under the existing daily budget. A separate consolidated-data audit confirms that two consequential IEX observations did not represent the consolidated market.

### Failed runs

| Scheduled run | Failed components | Evidence |
| --- | --- | --- |
| [17:35](https://github.com/Chiizzie/market-radar-ai/actions/runs/43069585938) | Approved-paper watcher | Six stale SLM polls; no unconfirmed notifications. |
| [17:40](https://github.com/Chiizzie/market-radar-ai/actions/runs/43070382322) | Both quote watchers | Nine stale SLM polls in each; comparison gap approximately 34.9 seconds. |
| [17:50](https://github.com/Chiizzie/market-radar-ai/actions/runs/43071970979) | Comparison watcher | Stale SLM/WU quotes, WU still missing at completion; initial restore delayed the first completed poll by 23.2 seconds. |
| [17:55](https://github.com/Chiizzie/market-radar-ai/actions/runs/43072747869) | Both quote watchers | Comparison: 25/65 error polls and a WU gap of approximately 79.8 seconds. Approved watcher: seven SLM errors and approximately 35.2-second recovery. |
| [18:00](https://github.com/Chiizzie/market-radar-ai/actions/runs/43073607375) | Both quote watchers | Comparison: 14/64 error polls and approximately 59.9-second maximum recovered gap. Approved watcher: three SLM errors, recovered within approximately 10.2 seconds. |
| [18:05](https://github.com/Chiizzie/market-radar-ai/actions/runs/43074347749) | Both quote watchers | Comparison: five stale SLM polls; approved watcher: four. Both recovered, but their existing completion criteria still returned failure. |

These are visible observation gaps, not new budget-settlement or dashboard-ingestion errors. The approved watcher still returns failure for any error poll, even a short recovered gap; the comparison watcher permits only narrowly bounded recovered gaps and also counts initial polling delays. A successful operational-report workflow means the report was produced, not that the underlying scan was healthy.

The 18:05 review job reported `budget_deferred`, zero model calls, and daily EUR 1 limit / EUR 0.878877 spent / EUR 0.028918 held / EUR 0.092205 available. Required headroom remains EUR 0.15. The lifetime limit is EUR 100 with EUR 95.440044 available at that check. No allowance was changed during this audit.

## Outcomes verified from the approved-paper journal

Journal read and replayed at approximately 18:16. Values include the existing fictional allocation and flat-cost assumptions, and are not the user's account P/L.

| Symbol | Recorded state | Recorded net EUR | Interpretation |
| --- | --- | --- | --- |
| LRCX | Entry 17:21:57; stop 17:24:15 | -25.922248 | Exit used an extreme IEX quote contradicted by nearby consolidated quotes; not evidence of a market-wide stop-out. |
| MOS | Entry 17:40:40; stop 18:00:46 | -3.755081 | The consolidated 18:00 minute traded below the planned USD 22.535 stop; the exact quote-window audit was still delayed/unavailable at its snapshot. |
| SLM | Entry 17:31:01; stop 18:12:25 | -5.534209 | New recorded stop, with prior monitoring gaps. Exact consolidated exit verification was not yet available within the free historical delay. |
| MTCH | No paper entry; trigger-gap rejection | Not applicable | Rejection used an extreme IEX ask; nearby consolidated ask remained below the trigger. This does not prove a later eligible fill. |
| FIGS | Watch expired without eligible entry | Not applicable | Pre-deployment watch; no paper trade. |

Original outcomes remain unchanged. There is no backdated replacement fill, deleted loss, invented winner, or live order.

## Independent quote evidence

[First read-only audit](https://github.com/Chiizzie/market-radar-ai/actions/runs/43075847906), as of 18:14:30, and [expanded audit](https://github.com/Chiizzie/market-radar-ai/actions/runs/43076218686), as of 18:16:45, used Alpaca's existing credentials, no model or messaging credentials, and bounded read-only requests. Raw responses are preserved in their workflow artifacts. Historical quote windows were 10 seconds wide and pagination truncation was checked; the cited windows were complete.

### LRCX

- IEX at 17:24:15.513063685: bid USD 228.91 / ask USD 249.81, spread 873.16bps (8.73%). This is the source of the recorded simulated stop.
- Consolidated quote at 17:24:15.487653428, approximately 25 milliseconds earlier: bid USD 240.78 / ask USD 240.88, spread 4.15bps.
- The first consolidated quote after the IEX observation, at 17:24:16.455433886, had the same bid/ask. Across the full 10-second window the consolidated bid ranged USD 240.70–240.87.
- Planned stop was USD 238.94. The observed consolidated quotes did not cross it. This is strong evidence that the IEX-only exit did not describe the consolidated market. It is not proof of a broker fill or of the trade's eventual profitability.

### MTCH

- IEX at 17:34:16.046652867: bid USD 40.97 / ask USD 42.51, approximately 368.95bps (3.69%) spread.
- Last consolidated quote before it, 17:34:15.366389370: bid USD 41.02 / ask USD 41.04, approximately 4.87bps spread. There was no later consolidated update within the remaining five-second window.
- Planned trigger was USD 41.10106. The IEX ask created a terminal gap rejection although the recent consolidated ask remained below the trigger.
- Code inspection confirms that `replay_long` checks breakout invalidation/gap before the entry-spread filter, and has no corroboration requirement for an exit. A new versioned protocol must address this without silently rewriting existing histories or assuming every wide quote is erroneous.

### Feed access and stale gaps

Latest IEX requests succeeded. Latest SIP returned HTTP 403 and explicitly reported a subscription restriction. Older SIP historical quotes and bars succeeded. SLM and WU had no IEX updates within sampled stale-gap windows while SIP did have updates. This supports a feed-coverage explanation; it does not establish continuous full coverage for either feed.

Alpaca documents IEX as a single exchange and SIP as consolidated exchange data. The free historical delay is suitable for retrospective auditing, not current entry decisions. Sources: [Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq), [Historical quotes](https://docs.alpaca.markets/us/reference/stockquotes-1). No subscription was purchased or changed.

## Setup quality

All four post-deployment approved watches used `trend_continuation_20bar_v1`. It requires positive measured momentum, close above rolling VWAP and recent volume at least its earlier baseline. The stop uses the last three candle lows; the target is a projection satisfying assumed net reward/risk. These conditions do not establish an edge.

MOS is a concrete weak candidate: measured 20-bar momentum was only 0.2441%, relative volume 1.0071x, and the last supplied price was approximately 0.68% below the first regular-session IEX open. Its planned USD 22.597575 entry and USD 22.535 stop were 0.2769% apart. Its retained news was a two-day-old analyst target cut, not a fresh positive catalyst. The AI rationales mainly established that the simulation was internally coherent and below the risk ceiling; that does not establish a compelling trade. A tight percentage stop alone is not proof of bad placement: this stop was approximately 1.73 times the simple 14-bar average true range on the supplied five-minute IEX candles.

SLM's measured relative volume was 3.94x and momentum 1.78%, so its failure cannot be explained by MOS's weak-volume case alone. The current sample is too small to infer a winning rule. The 18:09 report also had four closed code-only comparisons, all stops, approximately EUR -19.57; the execution problem is not solely an AI-vote issue.

## Next engineering work, not yet implemented by this audit

1. Version the handling of quote-quality failures across pre-entry invalidation, gap rejection and exits. Preserve suspicious evidence and mark uncertain outcomes explicitly; do not replace a stop with a later favourable price or infer a missed fill.
2. Make the live-feed limitation and uncertainty visible at the actual opportunity/result, not only in an offline report. Evaluate affordable verified real-time quote sources before considering an upgrade; the current account is not entitled to real-time SIP.
3. Define stronger opportunity-merit criteria separately from simulation eligibility, evaluate stop/target realism and market/sector context, then freeze the candidate rules for prospective testing. Do not tune a threshold solely to remove today's losers or widen existing stops retrospectively.
4. Distinguish short recovered paper-watcher gaps from critical gaps using explicit bounded health criteria, while retaining every error, missed-observation period and unknown result. Improve comparison startup restoration separately.

Only the read-only audit script/workflow and these notes were added in this follow-up. Trading rules, historical records, paid-review budgets and scheduled runtime pins were not changed.
