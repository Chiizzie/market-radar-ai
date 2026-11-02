# Market-open rehearsal, 3 November 2026

Goal: verify stock/crypto provider connectivity, fresh completed candles, coverage counts and frontend handling. This is not a trading-performance test or authorisation to trade.

In GitHub Actions open **Phase 1 verification**, choose **Run workflow** and explicitly select `phase-1/market-data-layer`. The public-data-capture job requests MSFT/AAPL/NVDA and XBTEUR/ETHEUR. It exports `capture.json`, `dashboard.json` and `readiness.json` in the `public-market-data` artifact. No paid AI steps run on manual dispatch because the budget job is push-only.

Run after sufficient regular-session five-minute bars have completed. A green software test alone is not a green data rehearsal: inspect readiness.json. Both markets must have current data and every attempted sample must pass for the rehearsal to pass. Empty/stale/error data fails rather than being replaced with demo data.

Dashboard JSON expires 60 seconds after export. A downloaded artifact will often already be expired by the time it is imported. That is expected historical-inspection behaviour, not a reason to extend or reset its timestamp. Local import is not a live backend connection. Verify symbols/counts and stale labels against the artifact; demo mode must remain separate. Live auto-refresh requires the authenticated endpoint still to be deployed.

Unverified broker eligibility, absent live news and missing real-market agent evaluation remain blockers to paper trade calls. Never interpret a successful data rehearsal as profitability evidence.
