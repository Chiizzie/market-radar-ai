# Market capture timeout — 9 November 2026

The 21:10 Dublin run 42699929751 used calendar-fix runtime 71742be and still timed out in market_data.capture after 240 seconds, before the calendar stage. Its independent crypto smoke check also failed. The logs do not attribute the stalled capture to a particular provider, so a Kraken outage is not established.

Capture previously queued 30 crypto histories with two workers, three attempts per request and potentially long backoffs. This can exceed the outer timeout during provider trouble. Capture now uses one five-second request attempt per pair, two at a time, and stops further requests after a fully failed batch. Remaining symbols receive explicit provider_circuit_open errors with no candles. Existing market-outage failure signals and risk gates remain intact. This reduces a known timeout risk; live recovery remains unverified. Full workflow may still fail for crypto unavailability or GitHub backup verification. Broader stock capacity and AI budgets unchanged.

Validation: 1,346 Python tests passed, including outage fanout stopping and isolated bad-pair handling.
