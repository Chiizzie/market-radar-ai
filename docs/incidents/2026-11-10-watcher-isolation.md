# Watcher isolation and storage read recovery

Approved-trade observation previously ran comparison replay synchronously before every journal poll. Several November 10 runs showed gaps exceeding 100 seconds; some failed solely because comparison processing failed. The underlying historical provider/HTTP errors were not recorded, so their precise cause cannot be established retrospectively.

Comparison now runs in a separate scheduled job, with its own observer and health artifacts. The original recovery export and receipt remain attached to that worker. Inline approved-trade observation also no longer starts a second comparison projection. Failed comparison jobs still fail the workflow; genuine paper quote gaps and notification failures still fail the approved watcher.

Signed event reads retry transient transport failures and HTTP 429/500/502/503/504 at most three times, with 0.5/1-second backoffs and existing 5/12-second connection/read timeouts. Signatures are regenerated each time. Writes are never retried after ambiguous acknowledgement. Authentication, malformed responses, and evidence/hash validation remain fail-closed. Review still requires durable comparison sync before paid model access.

Diagnostics record allowlisted failure causes, HTTP status and attempts for storage failures, timestamps, poll duration and comparison startup delay. Stock failures distinguish FX, market clock, quote fetch and validation stages. No provider response bodies, account information, tokens or arbitrary exception text are exposed. Freshness gates, original evidence hashes, risk/budget limits and live-order prohibition are unchanged.

Validation: 54 focused tests covering approved lifecycle, comparisons, observer, private holding monitor, operational receipts and new reliability regressions. Production observations are required to assess actual cadence after rollout. The new comparison job is directly visible in GitHub; the existing dashboard retains its six-job detail allowlist, while the overall workflow conclusion includes comparison failures.
