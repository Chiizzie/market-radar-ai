# Evening storage stall — 16 November 2026

## Confirmed failure pattern

The failures after the afternoon delivery repair are two different classes.

1. Scheduled scans at 17:15, 17:25, 17:50, 18:30, 18:35, 19:10, 20:00 and 20:05 Europe/Dublin failed quote-quality checks in comparison watchers (and the 17:50 paper watcher). Observed cases include long recovered gaps and unresolved TTEK, EQPT and MELI gaps. Do not weaken the freshness or recovery rules.
2. Around 20:35, the shared dashboard/storage path began timing out across independent jobs. Scan [43951305145](https://github.com/Chiizzie/market-radar-ai/actions/runs/43951305145) failed collection, account dashboard delivery, comparison observation, entry confirmation, method observation and manual alert auditing. Later manual portfolio, execution/readiness and operational-health workflows also failed. One failed source scan therefore leads to several additional failure emails from dependent reports.

Representative errors are `comparison_storage_unavailable:storage_timeout:attempts=3:http=None`. The 20:35 comparison watcher completed zero quote polls after startup and recorded repeated storage timeouts. Account sync reached its `dashboard_delivery` stage before failing; this is not evidence of a Trading 212 broker outage. In the 20:55 scan [43954700055](https://github.com/Chiizzie/market-radar-ai/actions/runs/43954700055), collection and account sync still failed, dependent research was skipped, and no paid diagnostic review was forced.

## Independent verification

Read-only hosted probe source `58698aeee11312b1a3c814cd8df3c3dde56c41bb`, [run 43954474101 / job 133605259079](https://github.com/Chiizzie/market-radar-ai/actions/runs/43954474101/job/133605259079), used the exact deployed EventClient from review source `bb3731f50a77972e547402f5c23e719e201ca973`.

At 20:54–20:55:
- The published app returned HTTP 200 in 1.084 seconds.
- An authenticated storage read with a cursor beyond every existing event still timed out after three attempts / 37.592 seconds.
- A read after known cursor 318094 also timed out after three attempts / 37.599 seconds.
- The probe made zero model calls, sent zero notifications and wrote zero storage events.

A page loading successfully does not establish that the data API works. Retrying entire paid reviews or widening client timeouts is not a demonstrated fix.

The database management connector was intermittent: some inspections returned 504 UNAVAILABLE, while SELECT 1 succeeded at 20:49:48. One activity snapshot showed 14 idle client connections and only the current active query, with no observed lock-wait pileup. The most recent row obtained was seq318094, received at 20:43:16. Database size was reported as 778 MB at 20:58:30. **That size alone does not establish a quota violation or capacity cause.** A timeout also does not establish whether a write was ultimately committed; preserve all event identities and histories.

## Recovery attempt and limits

Requested a republish of the unchanged verified dashboard commit `ebed71e30aa8a8292a176168e10ab92c3a7b0e2c`. Lovable returned pending deployment ID `3ef900b1-8180-48ed-bb3a-924e34df95fb`. The subsequent signed-read probe failed, so there is no verified storage recovery. Do not describe a pending deployment or generic project-ready metadata as successful restoration.

The connected API does not expose hosting runtime logs or a detailed deployment result. The project-controls browser was blocked by a separate sign-in requirement; no credentials were requested or entered and no paid Lovable editing agent was started. Root cause beyond the shared data-service failure remains unestablished. The public Lovable status page reported no broad incident at inspection; that does not exclude a project-specific fault.

Next required evidence: hosting/runtime logs and deployment status, database/API capacity and error metrics, then a successful signed read followed by fresh normal collection/account/report receipts. The dependent jobs share one storage service; restoring that path is the current priority. Keep the missing observation intervals and unresolved simulated outcomes explicit. Never fill gaps with later quotes or claim dashboard data current without fresh receipts.

All production runtime pins, model budgets, risk limits, quote thresholds, notification reservations and historical evidence remain unchanged. The incident investigation introduced only a read-only diagnostic workflow on its own branch and the same-version republish request. No trade orders or extra paid model calls were made.

See [machine-readable evidence](../evidence/storage-stall-20261116.json). The earlier [delivery repair](2026-11-16-alert-delivery-and-quote-gaps.md) verified one delivery component at 17:18; it was not a whole-system resilience result.
