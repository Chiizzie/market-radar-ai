# Market-open preparation and crypto rehearsal

Updated 2026-11-03. Repository: Chiizzie/market-radar-ai only.
Development branch: phase-1/market-data-layer.

## What is connected

Manual scanner dashboard capture now uses Alpaca IEX for all eight requested
stocks (NVDA, MSFT, AAPL, AMD, META, AMZN, GOOGL, TSLA), using existing
ALPACA_API_KEY and ALPACA_API_SECRET secrets. Kraken supplies the four requested
crypto pairs. The stock provider is selected explicitly; no silent Yahoo fallback.

Each stock request is one GET to the fixed Alpaca data host, bounded to 1 MB with
no redirects or retries. Symbols must match the response, pages must be complete,
and bars must be ordered, correctly aligned and finite. Only completed bars in
the current New York date's 09:30–16:00 window are retained. This window is a
data filter, NOT holiday/early-close/halt verification. Account eligibility,
calendar verification and consolidated market coverage remain separate gaps.

IEX is a single venue; its bars/volume are not consolidated US activity or
Trading 212 executable prices. Gaps stay visible rather than interpolated.
Native USD is preserved in evidence and the fresh EUR FX gap remains.
The older default CLI still uses Yahoo unless --stock-provider alpaca_iex is set.
Cache namespaces distinguish the two providers.

## Tomorrow: Wednesday 4 November 2026 (Dublin time)

The published regular US cash-session hours convert to 14:30–21:00 Dublin.
November 4 is not a holiday listed on the official 2026 NYSE calendar.
Refresh session evidence tomorrow; this planning note is not an admission input.

- Before/opening: run an unpaid capture to verify provider access, news,
  source identities, freshness, and bounded coverage. A successful workflow
  alone is not a call.
- 14:30 onward: accumulate this session's completed five-minute stock bars.
- About 16:10 earliest: twenty completed bars become available for the current
  ranker. Missing IEX bars or unavailable data can delay readiness. Do not relax
  the history requirement or substitute yesterday's data as current.
- During session: inspect readiness.json and candidate packages. Do not enable
  paid analysis unless a review is useful and the existing shared budget permits.
- All paper plans must respect actual session close, evidence expiry and the
  user's 22:00 Dublin cutoff. Crypto entries also stop at 22:00.

No recurring schedule or tomorrow background dispatch was enabled by this change.

## One free manual rehearsal

Open Actions → Manual scanner dashboard capture → Run workflow.
Choose phase-1/market-data-layer. Set candidate_market to crypto for an
after-hours test, or stocks for the stock-specific morning readiness check.
Leave paid_analysis and send_candidate_review false.
send_snapshot may be enabled to deliver the real research snapshot.

Inspect the uploaded artifact:
- capture.json: both markets' raw candle captures, success/failure and quality.
- enriched-capture.json: retained raw public EUR reference quote evidence.
- candidate-packages.json: research shortlist sources and missing evidence.
- readiness.json: current data/quote status, remaining gates, cutoff state,
  and deterministic expiry guard replays.
- candidate-review/status.json: dry_run and model_calls=0.
- dashboard.json: research-only snapshot; provider failures remain visible.

The readiness report deliberately separates research readiness from trade
readiness. Its future-time expiry checks are labeled deterministic replays,
not live future observations or completed paper outcomes. Every result retains
trade_authorized=false and orders_submitted=0. Actual paid agent reviews are
separate; a dry run does not claim the agents ran.

## Product state

The optional Lovable quote-panel update was approved and published in deployment
6cb644fd-ca6d-4788-a626-92df41ef48a8. Production quote code, protected access and
the prior real XRP review were verified on November 3. Older reviews have no new
quote inserted retrospectively.

Still required for actionable paper calls: account-supported broker eligibility,
executable quote/cost evidence, generic EUR plans, independent catalyst evidence,
fresh admission after review, and outcome tracking. This rehearsal does not clear
those gates, create a trade or imply proven profitability.

Sources checked 2026-11-03:
https://docs.alpaca.markets/us/reference/stockbarsingle-1
https://www.nyse.com/markets/hours-calendars

