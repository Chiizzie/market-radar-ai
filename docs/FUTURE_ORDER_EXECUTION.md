# Future automatic order execution — backlog only

User request, 3 November 2026: after the current research/paper project is complete,
consider automatically filling orders from qualifying calls. This records future
interest, not authorization to connect order permissions or place live trades.

Current scope remains Trading 212 Invest and Robinhood Europe crypto, EUR reporting,
maximum planned loss EUR20, intraday only, no entries at/after 22:00 Europe/Dublin.
No execution code, order credentials, live orders or schedules are enabled here.
Do not modify the independent Chiizzie/market-radar repository.

Before a separate execution phase:
- Verify official broker API support, account eligibility and permitted instruments.
- Establish a measured paper-trading record and review failures, costs and slippage.
- Define explicit human approval, capital allocation and execution-mode settings.
- Design idempotent order submission, reconciliation, partial-fill/cancel handling,
  broker-side protective orders, stale-price rejection and outage recovery.
- Define daily exposure/loss limits, manual kill switch and session-close handling.
- Revalidate every call at execution time; never execute historical dashboard rows.
- Test in supported broker sandboxes before requesting explicit live activation.

A EUR20 planned stop loss is a sizing constraint, not a guaranteed maximum realised
loss: gaps, slippage and broker/order failures must be assessed in that future review.
