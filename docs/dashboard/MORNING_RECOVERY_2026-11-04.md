# Morning recovery — 4 November 2026

The scheduled collector incorrectly treated intentionally unrequested regular-session Alpaca bars before open/weekends as failed connectivity. The provider now marks this explicit skip; capture excludes it from connectivity failures, while successful stock coverage stays zero and empty data remains NO_ACTION. Missing credentials and unexpected empty responses still fail. This does not claim an exchange-calendar check or premarket trading feed.

Backend fix: a1871d67330ec5e1ed0524506f2e777b4a3da8d2.
Main scheduler pin: 5133723de4b43af9729cee16373ec5f760ad4108.
Verified manual production run: https://github.com/Chiizzie/market-radar-ai/actions/runs/41817349105 (success).
Delivery generated 2026-11-04 10:55:29 Dublin; all eight stages succeeded, no failures, model calls zero. Four crypto rows current; eight stocks not actionable. Eight stock research briefings stored.
Snapshot id and independently queried database raw-body SHA256 both:
74a74089d81d7a1afb05e20ab7fe6774c908d1f176bd9447095c9f203131977f

781 tests passed before deployment locally and in GitHub CI. A further CLI regression confirms preopen skip exits zero while unexpected empty data exits one; full local suite then passed 782 tests.

## Scheduling remains unresolved
Morning cron executions were 08:18, 09:19 and 10:29, not the requested five-minute cadence. Successful manual execution does not verify timer reliability. GitHub documents that scheduled events can be delayed or dropped. Native cron remains enabled pending verification of an external replacement.

The user selected a separate cron-job.org job. Sign-in was rejected, so no external job was created or activated. Configure after sign-in:

- Name: Market Radar AI research collection
- URL: https://api.github.com/repos/Chiizzie/market-radar-ai/actions/workflows/scheduled-scanner.yml/dispatches
- Method: POST
- Body: {"ref":"main","inputs":{"verify_outside_hours":false}}
- Headers: Accept: application/vnd.github+json; Content-Type: application/json; X-GitHub-Api-Version: 2022-11-28; Authorization: Bearer <limited token entered securely by owner>
- Token scope: only market-radar-ai, Actions write (workflow dispatch). Do not reuse or expose model, broker or ingest secrets.
- Schedule: every five minutes, 08:00 inclusive to 23:00 exclusive, Europe/Dublin, daily. The backend independently enforces the same window.
- HTTP 204 proves dispatch acceptance only; verify resulting GitHub run and dashboard delivery.
- Verify two scheduled runs before removing native cron to avoid duplicate triggers. Do not modify the existing original scanner cron job.

No Lovable AI build was requested. Paid AI models and live orders remain disabled in this collector.
