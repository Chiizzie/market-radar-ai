# Recurring collector release verification

Verified overnight 3–4 November 2026, Europe/Dublin.

## Release and activation

- Backend release `2d8d77f599d649c9e3c68002c009ad53e2125a12`:
  779 tests passed locally and on GitHub run `41742854700` (test job
  `126288431783`, 779 passed in 7.85 seconds). Compile and offline scenarios passed.
- Main activation commit `af93a520b52566708fe085efc55f960327c8f6b7` adds only
  `.github/workflows/scheduled-scanner.yml`. It checks out the backend SHA above.
- Workflow is enabled: GitHub shows the Disable workflow option. The five-minute
  cron and the Dublin 08:00–23:00 guard are installed. First eligible morning
  target is 08:02 Dublin on 4 November; the actual timer-triggered run has not yet
  occurred. GitHub scheduling remains best-effort.

## Two real deliveries

Both were new manual dispatches of the scheduled collector on main, explicitly
using outside-hours verification. Neither was a rerun or a simulated response.
These prove collection, delivery and cache reuse, not the cron timer itself.

| Run | Result | Generated Dublin | Evidence cache |
| --- | --- | --- | --- |
| 41743118281 | Success, 45 seconds | 2026-11-03 23:57:43.602587+00:00 | Collected |
| 41743362830 | Success, 35 seconds | 2026-11-03 23:59:35.763672+00:00 | Reused original timestamps |

Stored snapshot IDs (also independently computed SHA-256 of the database raw body):

1. `38ce88381c56e8b4c95dc8a815616b1b50f29ed071351d9ed1dadc908608e73b`
2. `05eda283f04982faae689f8f40bc529060268624794799330f7432c5945ab973`

Both contain eight stock briefings and four crypto rows, zero agent reviews,
zero model calls and no trade authorization. All stock trading bars were stale
after hours; the four crypto rows were current research data at capture.
Collection reports contain no failed stages. The news feed retains explicit
partial-coverage information, including its unavailable Microsoft editorial feed.

Second run restored `scanner-evidence-v1-41743118281` successfully. The original
evidence collection start stayed `2026-11-03T23:57:34.710934+00:00`.
Database comparison confirmed news retrieval stayed
`2026-11-03T23:57:34.892997+00:00`, the first earnings calendar stayed
`2026-11-03T23:57:41.289010Z`, while the first stock context advanced from
`23:57:38.995664+00:00` to `23:59:33.647157+00:00`.
Snapshot expiry remains 60 seconds; no timestamps were refreshed to hide age.

## Frontend

Lovable plugin-reported commit `0d4af4e71e3dd55f1479abc64c7d6f273799b768`,
deployment `772b0cbc-85a5-490c-b023-8238f3b4650b`.
Lovable reports 396 passing tests, good typecheck/build, local existing-viewer
checks for paused/overdue states, mobile fit, source persistence and logout.
Its build reports 4.1 credits. No additional build request was started after the
user flagged low credits; publication and read-only checks used direct tools.

Independent production browser checks observed the collector timing panel,
sign-in guidance, unknown health when signed out, and persistence of a newly
selected Scanner feed across reload. Historical `mr-source=real` preferences
still restore the old endpoint choice until Scanner feed is selected once.
Production database checks confirmed both real signed deliveries and hashes.
The new protected UI was not independently re-tested with a signed-in browser
in this release; its local authorized-viewer check is reported by Lovable.

No automatic paid analysis, Telegram delivery or orders were enabled. No
profitability claim follows from successful scheduled-data integration.
