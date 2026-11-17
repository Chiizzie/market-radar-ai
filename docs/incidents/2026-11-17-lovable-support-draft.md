# Lovable support draft — 17 November recurrence — not sent

**Subject:** Recurring Cloud data API timeouts; ingestion still failing after load reduction

Please investigate and restore the managed database/data service while preserving all records.

Project: https://lovable.dev/projects/97051425-8afb-4ea6-bf3e-f6e5fc127ba3
App: https://pixel-perfect-replay-32614.lovable.app
Last observed instance: Tiny, Europe/Frankfurt.

On 17 November, the normal 20:00 Dublin scan passed. History reads slowed around 20:05; collection, account ingestion and research reads then failed across separate jobs. At 20:25 the scanner could not confirm snapshot delivery. The 20:50 collection still failed at 20:51:33.

A read-only GitHub-hosted probe at 20:39–20:40 returned HTML 200 but both signed empty-partition reads timed out after three attempts (about 37.6 s each). At 20:49–20:50 the same reads succeeded but took 21.890 s and 17.170 s. Management SQL alternates between results and UNAVAILABLE. Last verified scanner snapshot receipt was 20:21:08 Dublin.

Database size was 927 MB; postmaster start remained 3 November. Activity snapshots did not establish a blocking lock or connection exhaustion. Index catalog inspection failed, so index health remains unverified. Resource exhaustion is not yet proven.

We have stopped downstream history rebuilds after failed scans and deployed authenticated daily history checkpoints. These reduce repeated reads without deleting records, weakening validation or increasing timeouts. No new restart, pause/wake, instance upgrade, budget change or order action was made.

Please inspect compute/CPU credits, memory/OOM events, I/O and storage/WAL health, PostgREST/pool latency, platform ingress, and the earlier unresolved pause operation. Confirm the diagnosis and whether an instance change is required before any paid upgrade.

Evidence: https://github.com/Chiizzie/market-radar-ai/blob/main/docs/incidents/2026-11-17-storage-stall-and-history-cache.md

No credentials, raw account snapshots, private fills, positions or notification identifiers are included.
