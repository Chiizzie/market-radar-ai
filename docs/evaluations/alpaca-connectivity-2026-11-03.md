# Alpaca read-only connectivity — 3 November 2026

Verified with repository secrets ALPACA_API_KEY and ALPACA_API_SECRET. The new workflow performs three bounded GET requests to data.alpaca.markets: NVDA IEX latest quote, current-day five-minute IEX bars, and up to 20 NVDA news items from the preceding three days. No trading/account endpoints, paid AI calls, retries, or subscription changes.

## Verified capture at 16:08:09 Europe/Dublin

- Quote: bid $208.58, ask $208.61, IEX spread $0.03; 0.04419 seconds old at evaluation. Historical capture only, not a current price or entry recommendation.
- 19 completed five-minute candles; latest completed bar age 189.27 seconds, no internal gaps. One unfinished candle excluded. The 20-bar planner threshold was not met.
- News endpoint accessible: 20 returned records and a further page available. Headlines are external unverified evidence, not confirmed catalysts. This bounded capture does not claim exhaustive coverage.
- Local suite: 392 passed, including 16 Alpaca tests. GitHub Phase 1 verification run 41670963865 and Alpaca check run 41670963824 both completed successfully.
- Artifact hashes independently verified; full captures and workflow links are in the companion JSON.

The first run received candles and news but rejected the quote. Inspection found quote freshness was evaluated against request-start time, which can precede a newly arrived quote. Evaluation now uses response-arrival time; a deterministic regression test covers that race and future timestamps remain rejected. The second credentialed run passed all three endpoint checks. The first raw quote was not retained, so its exact rejection condition cannot be reconstructed.

## Boundaries and remaining integration

IEX is limited coverage, not consolidated NBBO or Trading 212 executable prices. The workflow's success means the diagnostic executed; always inspect individual statuses and timestamps. data_received can include stale or empty sections and must never be interpreted as a trade gate.

This is a fixed-NVDA connectivity adapter, not yet the scanner's general stock provider. Next: generalize validated symbol handling, connect provider provenance to the research packet and EUR paper planner without mixing feeds, preserve the limited-coverage flag, and run independent agent review against a complete paper plan. Account-specific broker eligibility, actual costs, exchange-calendar checks and actionable-plan review remain unresolved. No trade authorized.
