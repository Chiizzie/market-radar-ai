# All-session stock context research

The 20-completed-bar requirement belongs only to the baseline momentum and
relative-volume ranker. It does not apply to the context research path.

## Connected path

Every manual scanner capture now also requests bounded Alpaca IEX history for
each stock in the requested sample. Two read-only GETs per stock retrieve:
- Up to ten prior-date daily aggregates from a 21-calendar-day window.
- Up to 24 completed five-minute observations from 04:00 New York that day,
  including available extended-hours observations.

Today's incomplete daily aggregate and the unfinished five-minute bar are
excluded. Both requests retain their real time windows and original retrieval
time. Nothing relabels yesterday's data as today's current execution evidence.
These IEX aggregates are not official consolidated closes, complete US-market
volume, verified Trading 212 prices or broker eligibility. Corporate actions
remain unverified and no gap percentage is invented from mixed assumptions.

Historical data can be retrieved from the provider immediately; the project
does not need to observe a full trading day first. Artifacts preserve each
capture, but this is not a long-term database or learned trading memory.

A separate context-evidence-package-v1 is built for each stock with some
available evidence, even with zero completed current-session candles. It
separates exact symbol-linked stories from official Federal Reserve macro
context; a query alone never proves asset relevance. News queries now cover all
eight requested stocks, with a 50-item combined output cap and source failures
still visible.

Research phases are PREMARKET_CONTEXT, OPENING_CONTEXT, INTRADAY_CONTEXT,
AFTER_HOURS_CONTEXT or WEEKEND_CONTEXT, derived from the New York clock.
These labels explicitly do not verify an exchange calendar, holiday or halt.
Opening context is the first 100 minutes after the nominal 09:30 opening.

## Six-agent connection

Use review_scope=context and candidate_market=stocks (or auto) on Manual scanner
dashboard capture. paid_analysis defaults false. A dry run verifies a package
without claiming any model ran. When explicitly enabled, the same durable
shared AI budget funds six independent specialist reports, debate and conclusion.
The runner uses a separate context request-ID namespace and audit/result schema.

The agents consider changes since prior sessions, sourced catalysts, conditional
bullish/bearish scenarios, fresh confirmation required and invalidation. Their
conclusions are research only. The allowed verdicts remain REJECT,
MORE_EVIDENCE_REQUIRED or RESEARCH_WORTH_FOLLOWING. There is no BUY verdict,
plan, executable-price claim or order capability.

Context is CURRENT_CONTEXT_ONLY while the assembled package is valid. It never
uses the fresh trading-data label. Packages expire within five minutes and no
later than the oldest included retrieval's fifteen-minute limit. A bounded
review that finishes later becomes STALE_RESEARCH_ONLY.

review_scope=candidate preserves the older momentum-ranked stock/crypto path.
The 20-bar rule remains there. Existing v1 candidate reviews and dashboard
archives retain their contracts and reproducibility.

## Outputs and remaining work

Artifacts include context-capture.json, enriched-capture.json and
context-packages.json, plus candidate-review/package.json and (only for an
actual paid context run) audit/result/budget files.

Context reviews are not yet wired to a Lovable archive/UI or Telegram. The
runner rejects SEND_CANDIDATE_REVIEW=true in context mode before spending; the
existing candidate archive endpoint does not accept this new contract.
The existing scanner snapshot still reports current/stale candle data honestly.

This change adds research before and during the session; it does not itself
enable a recurring schedule or an automatic paid-model trigger. Continuous
collection still needs a separate scheduling and change-detection deployment.
No claim that agents are running unattended is warranted.

Source: https://docs.alpaca.markets/us/reference/stockbarsingle-1

## Verified 2026-11-03

Implementation commit: 02f8f48106c8c0485e5f71649e937a424821928e.
Local full suite: 703 passed. GitHub Phase 1 verification run 41735374673:
703 passed, compile checks and budget-storage verification successful.

Live manual run 41735765098 completed successfully in 35 seconds, with
review_scope=context, candidate_market=stocks, paid_analysis=false,
send_candidate_review=false and send_snapshot=false. All eight stocks returned
ten prior-date daily aggregates and 24 completed intraday observations.
The last prior-date daily bar was November 2. Available extended-hours bars
appeared for AAPL, AMD and AMZN; other stocks ended at the regular-session bar.
These observations were correctly retained as historical context, not fresh
execution evidence. Eight AFTER_HOURS_CONTEXT packages were assembled; their
canonical JSON was reproduced exactly from the downloaded capture and news.
The runner validated the first package (NVDA) with ready_dry_run and zero model
calls. No live six-agent context review, dashboard delivery or order occurred.

All eight company news queries returned leads, but none of this capture's
stock stories passed exact symbol relevance into the context packages. No
current Federal Reserve item qualified either. One editorial source failed,
and the combined feed reached its 50-item cap. News coverage remains partial;
these packages demonstrate history/context plumbing, not verified catalysts.

Artifact 13279181354 SHA-256 was independently checked:
27bddf5afca346fc61ffeb3ca8acf0003324222c77d0a243340e2fd43e11ebc5.
The test suite covers premarket research with zero current-session bars and
the six-role/debate/conclusion sequence using test clients. Premarket live
capture and a paid context review remain unverified.

