# Owner-requested pause — 25 November 2026

The owner requested a break from trading until the start of December. All ordinary scanner jobs and the five related automatic reporting/health/recovery workflows are guarded off before runner allocation. Incoming external dispatches may still appear in Actions, but their jobs are skipped. Historical data, runtime pins, budgets and risk controls are preserved.

No automatic restart is configured. Resume when the owner is ready in December by reverting this pause commit through a reviewed PR. Existing runs started before the pause retain their original configuration and must finish or be cancelled; verify no old scanner run remains before confirming the pause. CI remains available. No orders or test notifications are sent.
