# Wide scan calendar rate-limit incident — 9 November 2026

The 20:45 and 20:50 Dublin scheduled collections failed after expansion to 1,200 technical checks and 80 detailed stocks. The 20:50 run checked 1,200 charts, delivered 79 stock and 30 crypto snapshot records, but 19 of its 79 separate Finnhub calendar requests returned rate_limited. Calendar failure propagated to the collection job, skipping downstream review and market context. Paper watcher and account sync succeeded.

Fix: fetch the 15-day market-wide calendar window once, omitting the optional symbol filter, then partition and validate records by exact requested symbol. Preserve original retrieval time, raw response digest, per-symbol schema/checksum, 20-event bound, incomplete-coverage labels and all risk gates. Bound the shared response to 4 MB and 10,000 rows. No retry fan-out. Errors remain errors; empty results do not prove no event. No subscription, budget, trading-mode or breadth changes.

Validation: 1,344 Python tests passed. New tests cover 80 symbols/one request, identity partitioning, provenance, HTTP and malformed/oversized responses, and isolated invalid event records. Runtime 71742be520b76049b23d576657a42d9a0f8edb1e. Live recovery remains to be verified after deployment; existing in-flight runs use the earlier runtime.

Provider reference: https://pkg.go.dev/github.com/Finnhub-Stock-API/finnhub-go@v1.2.1 — EarningsCalendarOpts documents Symbol as optional.
