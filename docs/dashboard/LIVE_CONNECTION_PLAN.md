# Authenticated dashboard connection

## Verified deployment and signed delivery — 3 November 2026

Published dashboard: https://pixel-perfect-replay-32614.lovable.app
Stored reviews: https://pixel-perfect-replay-32614.lovable.app/stored-reviews

The user approved publication. Lovable reports published=true; browser inspection
confirmed the deployed app and invite-only sign-in gate for stored reviews.
The approved account has the viewer role; no browser write permissions are granted.

GitHub run 41714670873 successfully delivered snapshot
874571f09e452882fbd78c8c262bc42d1b792650c27d359a6fb827637963b50b
at 20:40:34 UTC. The sender verified HTTP 200, ok=true and matching snapshot ID.
The source was completed eight-stage review run 41706847328, artifact 13267625033,
SHA256 6afdca4c5694ec8bbb44e711ca87e61755565c5e88a1088712f0dcecf637156b.
All four source files are digest-pinned and the audit is replayed before export.
This delivery made no new AI calls and sent no Telegram notification.

The historical verdict remains MORE_EVIDENCE_REQUIRED. Original timestamps and
expiry are preserved. Completion and archive storage do not authorize a trade.

## Implementation and verification

`dashboard/lovable_delivery.py` signs exact UTF-8 timestamp + dot + body with
HMAC-SHA256. REVIEW_INGEST_SECRET stays server-side in GitHub and Lovable.
The published destination is fixed. Redirects, duplicate HTTP 409, timeouts and
mismatched acknowledgements do not count as delivery. No automatic retry occurs.
Historical archives may be expired; the UI must continue treating them as such.

Lovable hardening commit 88aae6a4b3e9aef57438de6ad8e0142db1506af2 added streaming
2 MiB limits, canonical timestamps, signature checks, unique snapshot IDs,
strict paper-review parsing, invite-only auth and viewer-only SELECT policies.
Lovable reported 170 tests/typecheck passing; these are provider-reported checks.
No client insert/update/delete permissions, public signup or automatic role grants.

Backend commit e38cb255db91db8ddd7da8b26266d9572d2494ab: 549 local tests passed;
GitHub verification run 41714538100 passed. Manual archive workflow registration
exists on main but execution is restricted to phase-1/market-data-layer.

Fresh paid reviews have an explicit send_lovable_review option, default false.
A delivery failure is recorded separately and cannot restart paid analysis.
The standalone archive workflow uses the pinned historical artifact without AI.
GitHub artifact retention limits future replays; the database holds the delivered
archive. Duplicate delivery is intentionally rejected and cannot overwrite it.

## Published viewer acceptance check

Lovable verification message umsg_01m6hj9cjaernt847wdzccacfh completed successfully.
Its database inspection found exactly one matching row received at 20:40:34 UTC.
Published-site browser testing with the approved viewer listed and opened that
review: all eight stages, EUR plan values, original times (19:50:45 evaluated,
19:51:38 completed, 19:55:00 expired), five blockers and MORE EVIDENCE REQUIRED.
The page retained expired/nonactionable warnings and reported no runtime errors.
Signed-out access exposed only the login form. Root independently inspected the
published sign-in gate and verified the GitHub delivery acknowledgement.
The older bundled example has a different snapshot ID and is not this delivery.

## Remaining scope

This milestone connects stored research reports. The general scanner snapshot
endpoint remains disconnected. Recurring scans and paid scheduling are not enabled.
Trade-call evidence gates remain closed until broker account eligibility, costs,
freshness and adequate independent evidence pass. Live orders remain disabled.
