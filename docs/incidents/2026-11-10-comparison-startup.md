# Comparison startup and quote diagnostics

The 20:05 Dublin comparison worker spent 158 seconds on its first poll. The approved watcher independently recorded 66 quotes in 66 polls, with a maximum five-second gap. The comparison failure was one rejected stock quote, not a recorded storage exception.

Replay previously opened/committed a SQLite connection and appended the export separately for each event. It now validates page identity/hash/order/cursor first, applies each page in one atomic transaction, and writes its lossless export in a batch. Individual enrolment, review, timestamp, immutable quote and cost checks remain active. Invalid page payloads roll back without advancing the cursor or export. SQLite remains a disposable projection of signed durable events.

A local 3,001-event synthetic replay measured 0.802 seconds before and 0.139 after. This is not a live latency guarantee or proof that SQLite explained all 158 seconds. Initial and subsequent sync metrics now separately disclose page/event counts, storage read time and projection time.

Rejected stock quotes now carry bounded symbol/reason diagnostics (missing, stale, future, crossed, nonpositive/nonfinite, currency, malformed). Up to 20 recent failures are retained. No response bodies or arbitrary exception strings are copied. Missing observations still fail the comparison job and freshness limits are unchanged.

Validation: 106 focused tests passed, including atomic rollback, identical outcomes and byte-for-byte exports versus individual replay, retry safety, diagnostic redaction, lifecycle and private holding monitoring. Live startup timing remains to be verified after rollout.
