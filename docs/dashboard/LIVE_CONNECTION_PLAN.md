# Authenticated dashboard connection: pending Lovable approval

Readiness check on 3 November 2026 found no enabled Lovable Cloud database or
sign-in. Current report imports and vendored examples remain browser-only.
The plan is awaiting human review in Lovable (`plan--show`,
`{"path":".lovable/plan.md"}`). No live endpoint is deployed.

Proposed implementation:
- Enable Cloud storage and invite-only sign-in with a viewer allowlist.
- Store strict paper-review-dashboard-v1 exports; reject fixtures and any order
  authorization. Client roles may not insert, update or delete records.
- GitHub sends a signed POST using REVIEW_INGEST_SECRET held server-side in both
  services. Sign exact UTF-8 bytes `timestamp + "." + raw_body` with HMAC-SHA256;
  reject noncanonical timestamps, more than five minutes skew, invalid signatures,
  oversized bodies and malformed reports. Snapshot IDs are unique; duplicates
  must not overwrite existing records. Never log authentication headers.
- Require authenticated allowlisted reads; CORS alone is not authorization.
- Browser revalidates reports and recomputes expiry. Stored research stays
  nonactionable, regardless of freshness. No broker/OpenAI secrets in the UI.
- Before production: test unauthorized reads/writes, signature failures, duplicate
  handling, expiry and isolation. Publish only the authenticated implementation.

After approval the user must create the viewer account and set the shared ingest
secret through secure settings (never chat). A stable published endpoint is needed
for GitHub delivery; preview access is not a production backend connection.
Recurring paid scans are not enabled by this plan. Their cadence must fit the
shared budget and verified session/expiry gates; a completed research review is
not a trade recommendation.

## Sender implemented — 3 November 2026

User reports REVIEW_INGEST_SECRET saved in both services. Lovable commit
c07ca6f1555b20ad213666ab9ddd3b678ddf0c9a implements HMAC ingestion and stored reviews;
its agent reports 150 tests/typecheck passing and invalid-signature HTTP 401.
Those checks do not prove a real GitHub delivery or authenticated viewer access.

`dashboard/lovable_delivery.py` revalidates the complete audit against source
evidence and signs exact UTF-8 bytes with timestamp + dot + body. The destination
is fixed to this project's ingestion endpoint. Redirects, duplicate HTTP 409,
timeouts and mismatched snapshot acknowledgements never count as confirmed.
No automatic retry occurs. Unlike fresh Telegram alerts, archived historical
reviews may already be expired; original expiry and nonauthorization are retained.

The manual paid review workflow has an optional `send_lovable_review` input,
default false. The secret is supplied only on that explicit path. Archive failure
is recorded separately and does not invalidate or rerun the paid review.
Full local suite at this stage: 548 passed. No real delivery has been attempted;
the app is not yet published and no viewer account has been verified.

Before publication: Lovable is tightening streaming body limits and testing
unauthorized access, duplicate insertion and the approved invite-only setup.
