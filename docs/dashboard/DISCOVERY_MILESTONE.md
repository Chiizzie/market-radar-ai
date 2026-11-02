# Discovery-to-dashboard rehearsal

Command: `python -m market_radar_ai.market_data.rehearsal --output-dir artifacts/discovery`

Stages: download both US stock directories and Kraken EUR catalogue; validate directory schema/membership and freshness; update local persistent queue; select five stocks and three crypto pairs; capture completed five-minute candles; export dashboard JSON and readiness report. No AI calls, broker credentials or orders.

Stock-directory footer format follows https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs. The source does not provide a timezone in the footer: validation uses its calendar date with a four-day maximum age and rejects future dates. It deliberately does not invent a precise UTC creation timestamp. Retrieval must be within one hour. Four days is a research policy allowing weekend files, not an exchange guarantee. Price/provider identity remains subject to per-capture checks and broker eligibility stays UNKNOWN.

`pipeline_completed` means the stages ran and exported files. `data_rehearsal_passed` separately means both markets had current data and all attempted samples passed. After the stock session, a completed pipeline may correctly fail freshness. Neither field means trading_ready.

Artifacts: stock-discovery.json, crypto-discovery.json, universe.json, capture.json, dashboard.json, readiness.json, rehearsal.json and scan-queue.sqlite3. A failed discovery preserves diagnostics and does not replace a pre-existing queue. Preserve/reuse the output directory to retain rotation locally. GitHub uploads a queue checkpoint but does not yet automatically restore it on a fresh runner; no unattended recurring scan is enabled.

Import dashboard.json into the Lovable preview using Import JSON. Original expiry remains in force; a downloaded file will usually be stale. This is historical inspection, not a deployed live endpoint.

Coverage is the filtered US listing subset and Kraken EUR pairs, not global stocks or Robinhood-confirmed assets. The first batch is fair alphabetic rotation, not a liquidity-ranked opportunity shortlist. Paid models, news evidence, broker verification, FX-normalised plans, and annotated live charts remain outside this milestone.

## Verified live milestone — 2 November 2026, 21:30 Dublin

GitHub run: https://github.com/Chiizzie/market-radar-ai/actions/runs/41528841099

Software tests, budget-storage verification and discovery-rehearsal jobs all succeeded. The pipeline completed and exported its artifacts. Readiness was separately FALSE:

| Market | Discovered subset | Attempted | Deferred | Current | Unusable/stale |
|---|---:|---:|---:|---:|---:|
| Stocks | 6,941 | 5 | 6,936 | 0 | 5 |
| EUR crypto | 490 | 3 | 487 | 3 | 0 |

The stock directory also recorded 6,338 source-row exclusions. This count includes excluded security types/test issues/symbol forms; it is not a count of unavailable broker assets. No candidate received agent review. These results verify discovery, bounded retrieval and export, not full-market quote coverage, broker eligibility or trade readiness. Individual stock failure causes are in capture.json; the summary alone does not establish each cause.

Download `discovery-to-dashboard` (artifact ID 13180851714, retained 30 days), extract `dashboard.json`, open the Lovable project and use Import JSON. The stale label is expected for historical data. Lovable project: https://lovable.dev/projects/97051425-8afb-4ea6-bf3e-f6e5fc127ba3

Lovable import update commit a835c58083341d2ac6f990598a8748cd10895cf4 reports 53 passing tests, passing type checks and a browser walkthrough; the local-import code and schema-1.0 actionability block were also inspected through the connector. Its tests were not independently rerun in the Python workspace. The frontend remains unpublished and no hosted endpoint exists.

Backend: 207 tests passed locally and GitHub software checks passed. No paid OpenAI call was made in this run. The temporary push activation was removed after verification; manual workflow dispatch remains available. Subsequent run summaries now print per-symbol provider status, candle count and quality issue codes to make failures inspectable without downloading the full artifact.
