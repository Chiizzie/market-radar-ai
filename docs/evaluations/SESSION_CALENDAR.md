# US equity calendar verification

The fresh review runner captures the current New York trading date through a
fixed GET to https://paper-api.alpaca.markets/v2/calendar. Existing Alpaca secrets
are used only as authentication headers; redirects, account requests and order
requests are not supported. The response is reduced to session date/open/close,
source, status and observation time. Failures retain no provider body or secrets.

Reference: https://docs.alpaca.markets/us/v1.1/reference/getcalendar-1
The documented calendar includes market holidays and early closes.

The planner revalidates evidence age (at most 300 seconds), exact trading date,
regular-session bounds, completed candles within that session and current time.
It blocks missing/error/closed evidence supplied by the runner. Valid evidence
clears only exchange_calendar_not_verified. Exit is the earlier of five minutes
before the provider's close or 22:00 Dublin. No new entries within that close
buffer. This verifies the regular US equity schedule, not symbol halts, broker
availability or guaranteed fills. Other eligibility/cost/catalyst gates remain.

Calendar evidence is retained inside the market capture and therefore bound into
the existing source hash and deterministic review replay. Legacy captures without
calendar evidence remain reproducible and keep the calendar blocker.

Local validation: 460 tests passed. Early-close tests use controlled synthetic
calendar responses; they do not assert that a particular date actually closed early.
Live provider validation is recorded separately below after artifact inspection.

Live verification: GitHub dry run 41685640530 on commit
7e9015ff0001bac2603fa37d8a37491b18d0127f returned ready_dry_run with zero model
calls. Calendar observed 2026-11-03T17:37:07.873321+00:00 reported 09:30–16:00
New York. The conditional draft exits by 20:55 Dublin, has no calendar blocker,
and retains all other five input blockers. The calendar-bound packet was
independently reproduced from saved artifacts. Full test job in run 41685640541
passed. No paid review or live order was triggered by this milestone.

Artifact SHA256:
e865d3a0de6ff75dac2758b40e7791da913736b9b11e73565074dd67d8495b9d
