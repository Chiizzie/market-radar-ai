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
