# External scheduler verification — 4 November 2026

cron-job.org job 8790954 is dedicated to market-radar-ai. The original scanner job 8651177 was not modified. The owner entered the GitHub credential directly; its value was not read or copied into code/logs.

Configuration: POST the scheduled-scanner.yml workflow dispatch endpoint on main, with verify_outside_hours false; every five minutes 08:00–23:00 Europe/Dublin, daily. Backend clock, repository, workflow-ref and attempt guards remain unchanged. No paid model or order credentials are supplied.

Initial test returned HTTP 502 and did not produce a GitHub run. One retry returned HTTP 204 at 11:21:37 Dublin. Run 41820227222 succeeded and delivered snapshot 6aa2e18d7d9612b4fb649b02b0c85ed4e252852a74878a2db6cd6a80b2686cab at 11:22:11.113612.

The job was then enabled. First automatic run 41820692434 was created at 11:25:09 and succeeded. Delivery at 11:25:34.409977: snapshot 4c283343d2ec000b64cacc66a8fbd68bce291c8d1bc4f5b5c0ff1edff1bd9e35. Database raw-body SHA256 matched both receipt IDs. The automatic run reused news/calendar evidence collected at 11:22:03.230833 without redating it; market/context/quote stages ran fresh. No failures; model calls zero; trade_authorized false.

Second automatic run 41821435373 was created at 11:30:31 and succeeded. Delivery at 11:31:01.204204: snapshot 96db9ee91297e0bc0cafe467f04f1be21f3120c90bac061e5940a97debe59243. Database raw-body SHA256 matched. Cached evidence retained its original timestamps; no failures, model calls zero. cron-job.org showed the automatic 11:30:29 dispatch successful and the next execution at 11:35.

After both automatic deliveries were verified, the overlapping native schedule stanza was removed from main. workflow_dispatch, implementation pin and operating-hour guards remain unchanged. This is a target cadence, not a guarantee of uninterrupted service; the initial 502 remains recorded above.

Successful collection is research delivery, not a six-agent trade call. Stock regular-session captures remain unavailable before open; four crypto rows were current research. Snapshot trade expiry remains 60 seconds.
