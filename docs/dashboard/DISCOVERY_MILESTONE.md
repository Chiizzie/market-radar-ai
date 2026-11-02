# Discovery-to-dashboard rehearsal

Command: `python -m market_radar_ai.market_data.rehearsal --output-dir artifacts/discovery`

Stages: download both US stock directories and Kraken EUR catalogue; validate directory schema/membership and freshness; update local persistent queue; select five stocks and three crypto pairs; capture completed five-minute candles; export dashboard JSON and readiness report. No AI calls, broker credentials or orders.

Stock-directory footer format follows https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs. The source does not provide a timezone in the footer: validation uses its calendar date with a four-day maximum age and rejects future dates. It deliberately does not invent a precise UTC creation timestamp. Retrieval must be within one hour. Four days is a research policy allowing weekend files, not an exchange guarantee. Price/provider identity remains subject to per-capture checks and broker eligibility stays UNKNOWN.

`pipeline_completed` means the stages ran and exported files. `data_rehearsal_passed` separately means both markets had current data and all attempted samples passed. After the stock session, a completed pipeline may correctly fail freshness. Neither field means trading_ready.

Artifacts: stock-discovery.json, crypto-discovery.json, universe.json, capture.json, dashboard.json, readiness.json, rehearsal.json and scan-queue.sqlite3. A failed discovery preserves diagnostics and does not replace a pre-existing queue. Preserve/reuse the output directory to retain rotation locally. GitHub uploads a queue checkpoint but does not yet automatically restore it on a fresh runner; no unattended recurring scan is enabled.

Import dashboard.json into the Lovable preview using Import JSON. Original expiry remains in force; a downloaded file will usually be stale. This is historical inspection, not a deployed live endpoint.

Coverage is the filtered US listing subset and Kraken EUR pairs, not global stocks or Robinhood-confirmed assets. The first batch is fair alphabetic rotation, not a liquidity-ranked opportunity shortlist. Paid models, news evidence, broker verification, FX-normalised plans, and annotated live charts remain outside this milestone.
