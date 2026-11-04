# Stock reference checks

Scheduled collection enables `ENABLE_STOCK_CHECKS=true` after calendar enrichment. It saves timestamped, checksummed `stock_reference_checks` in the enriched capture, with a validated summary in readiness.json. Each provider fails independently and records a redacted status. No order endpoints or paid AI calls are used.

Checks cover:
- Selected-symbol IEX bid/ask, positive size, noncrossed prices, source timestamp no older than 30 seconds, explicitly USD.
- Indicative USD-to-EUR conversion only when the existing FX adapter supplies a positive rate no older than 15 minutes.
- Alpaca US market clock, checked for timestamp freshness and next-open/close ordering. It does not prove individual stock halt status or broker trading availability.
- Trading 212 USD stock/ETF catalogue candidates for exact `SYMBOL_US_EQ` ticker strings. This is candidate matching, not independent ISIN/exchange identity verification or account permission. Missing/ambiguous matches remain unknown.

The raw capture expires from readiness after 60 seconds, and each source retains its stricter individual expiry. No timestamps are refreshed on evaluation. Reference quotes are not Trading 212 executable quotes; fees, slippage, account buy permissions, instrument halt status and EUR trade plans remain blocking.

Validated records now enter session briefings as optional stock-briefing-reference-v1 context evidence. The frontend strictly validates identity, times, prices and EUR presence and shows reference expiry. All six agents can cite the original context source containing these frozen checks. A quote can expire during model processing; its original expiry is never extended. Fresh FX clears only the missing-FX flag when every covered stock has a converted reference. Broker permission, executable price, fee and EUR plan gates remain. Existing archives without these fields remain supported. This change has offline exporter/parser compatibility tests; a paid live review using the new fields still requires budget headroom and an available review slot.

Documentation used: https://docs.alpaca.markets/us/reference/stocklatestquotes-1 and https://docs.alpaca.markets/us/reference/legacyclock .
