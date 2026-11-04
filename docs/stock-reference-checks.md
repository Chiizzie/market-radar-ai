# Stock reference checks

Scheduled collection enables `ENABLE_STOCK_CHECKS=true` after calendar enrichment. It saves timestamped, checksummed `stock_reference_checks` in the enriched capture, with a validated summary in readiness.json. Each provider fails independently and records a redacted status. No order endpoints or paid AI calls are used.

Checks cover:
- Selected-symbol IEX bid/ask, positive size, noncrossed prices, source timestamp no older than 30 seconds, explicitly USD.
- Indicative USD-to-EUR conversion only when the existing FX adapter supplies a positive rate no older than 15 minutes.
- Alpaca US market clock, checked for timestamp freshness and next-open/close ordering. It does not prove individual stock halt status or broker trading availability.
- Trading 212 USD stock/ETF catalogue candidates for exact `SYMBOL_US_EQ` ticker strings. This is candidate matching, not independent ISIN/exchange identity verification or account permission. Missing/ambiguous matches remain unknown.

The raw capture expires from readiness after 60 seconds, and each source retains its stricter individual expiry. No timestamps are refreshed on evaluation. Reference quotes are not Trading 212 executable quotes; fees, slippage, account buy permissions, instrument halt status and EUR trade plans remain blocking.

These records are currently diagnostic evidence in workflow artifacts/readiness. The strict AI and dashboard archive contracts have not yet been extended to consume these new fields; do not describe these checks as live trade admission or claim an AI review used them. Next work: versioned evidence-source contracts and corresponding frontend validation, then paper-plan admission.

Documentation used: https://docs.alpaca.markets/us/reference/stocklatestquotes-1 and https://docs.alpaca.markets/us/reference/legacyclock .
