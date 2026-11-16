# Lovable support draft — not sent

Prepared 16 November 2026, Europe/Dublin. Contacting support requires explicit user instruction; the existing approval covers database pause/wake only. The selected project is Pixel Perfect Replay. No attachments are selected.

**Subject:** Cloud data API outage; pause/wake did not establish recovery

Please investigate a managed Cloud database/data-API outage and restore service while preserving all records. This is a platform hosting-control issue, not a request to debug application code.

Project: https://lovable.dev/projects/97051425-8afb-4ea6-bf3e-f6e5fc127ba3
Published app: https://pixel-perfect-replay-32614.lovable.app
Region/instance: Europe (Frankfurt), Tiny.

On 16 November 2026 (UTC = Europe/Dublin), authenticated research-event reads and snapshot/account ingestion began timing out around 20:35. An independent read-only probe at 21:42-21:43 confirmed that even a signed read beyond the last possible event sequence times out after three attempts (37.6 seconds). The public home page still returns HTTP 200.

Database-management queries intermittently return 504 UNAVAILABLE. PostgreSQL logs showed repeated statement timeouts, an advisory-lock wait at 21:04:47 and an archive-command failure at 20:41:08. The resource panels displayed no pressure alerts, but storage usage was unavailable; resource exhaustion is not proven.

An unchanged app republish did not restore signed reads. A controlled pause was requested around 21:12. By 21:24, settings reported that the database was being paused; the Database page showed Project paused, with Wake up disabled and the explanation Project can be woken up in a few minutes. A database query returned Database is possibly not accessible at the moment.

At 21:41, table listing returned, but PostgreSQL still reported the original postmaster start time of 2026-11-03 19:41:55.979084 UTC. A subsequent event query returned 504, and the independent signed-read probe failed again. No completed restart is established. A second pause was not submitted; our execution approval safeguard blocked it as a possible duplicate.

The owner has approved pause-and-wake recovery. Please inspect the lifecycle operation and database/API errors, and restore the managed services while preserving data and credentials. No removal, restore rollback, instance upgrade, data deletion or code rollback is authorized.

Independent probe (zero models, notifications or writes):
https://github.com/Chiizzie/market-radar-ai/actions/runs/43954474101/job/133633988979
Incident record:
https://github.com/Chiizzie/market-radar-ai/blob/main/docs/incidents/2026-11-16-evening-storage-stall.md
