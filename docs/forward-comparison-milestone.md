# Forward comparison and cross-scanner audit — 7 November 2026

This milestone connects the existing comparison engine to durable production
storage and observes code-qualified candidates before paid selection. It does
not establish profitability. The original market-radar repository is unchanged.

## Prospective comparison

`PAPER_COMPARISON_ENABLED=true` connects scheduled paper review and the overlapping
five-second watcher to the dashboard's PostgreSQL `research_events` table. All
packets qualifying at the scheduled review's current qualification point are
enrolled before budget/selection filters. Preliminary screening alone is not
enrolment. Existing setup IDs retain their first entry window. The first quote
attempt completes before model generation; a local observer continues during the
review, while independent workers recover the same cohort, including unreviewed
and rejected candidates. No new AI calls or spending limits are introduced.

The two arms retain the existing fixed protocol in `paper_comparison.PROTOCOL`:
same observed bid/ask stream, original baseline entry window, fresh approval
clock for the AI arm, EUR plan costs, maximum EUR20 planned loss, no overnight
entry or exit. Venue and local receipt timestamps remain distinct; no look-ahead
or later backfilling of a missed entry. Rejected outcomes are hypothetical only.
Unknown costs and incomplete outcomes stay unknown. Closed-only drawdown is not
portfolio or intratrade drawdown. Capital constraints remain unmodelled.

Database writes and reads use the existing HMAC secret, fixed endpoint, clock
skew checks, streamed request cap and immutable SHA256 event IDs. Concurrent
inserts acquire a database partition lock before allocating their sequence
numbers, so a reader cannot skip a late lower-sequence commit. Database roles
deny anonymous access and viewer writes; viewers can read summary events only.
The producer cannot UPDATE or DELETE the evidence. It validates review chains
against a disposable SQLite projection before committing them permanently.

The SQLite file is disposable. Each worker replays the day's authenticated
events; original payload bytes and hashes are preserved in a JSONL export.
Compressed event exports are saved by successful watcher runs finishing between
22:00 and 22:15 Dublin, with 30-day artifact retention. Routine runs upload
summary/health files only to avoid repeatedly archiving the whole day. An outage
through that backup window can leave the secondary export missing.
These are secondary recovery copies, not the primary database. The restore test
reconstructs both comparison arms from JSONL and checks identical reports. No
claim is made about a paid Supabase point-in-time-recovery plan. Long-term backup
retention beyond these exports remains a separate operations improvement.

Observation capacity is 40 unique stocks and 30 crypto pairs. Deferred capacity,
errors, quote counts and poll gaps are disclosed. Five seconds is a target, not
a guaranteed feed; Actions startup gaps, provider latency and outages can still
miss price events. No unobserved result is converted into a win or zero return.
Storage failure before review prevents new paid generation. A later failed write
remains visible as an operational gap and retains local artifacts for diagnosis.

Dashboard `/performance` shows the latest daily, protocol-specific comparison
summary and the original-scanner audit. It never merges synthetic or earlier
strategy versions. Current rule/prompt version defines this new forward cohort;
future rule changes create another protocol. Evaluate later unseen periods before
changing rules based on returns. Reports do not activate orders or alerts.

## Read-only original-scanner audit

`dashboard.cross_scanner_audit` reads only the public original scanner's
`radar-alert-live/radar_alert.json`. It stores the source digest, original and AI
capture times and a reason per original actionable/watch signal. It distinguishes
discovery deferral, missing trace, capture rejection, code/risk blockers and an
actual recorded AI decision. It runs after collection and after review.

The maximum capture pairing gap is ten minutes, with both captures no more than
30 minutes old. These are near-time comparisons, never a claim of identical
prices or venues. Stale/unavailable feeds and missing symbol traces stay unknown.
The rolling original feed can overwrite short-lived alerts between polls, so
this is explicitly published-feed coverage, not a complete original alert ledger.
No original alert is copied into the AI candidate pool and no profitability is
inferred from an alert. Read access does not alter either scanner's strategy.

## Acceptance checks

- Prospective baseline quote precedes review-start event.
- A rejected candidate can close its hypothetical baseline without becoming an
  approved paper trade; approved and unreviewed arms remain distinguishable.
- Restarted workers recover cohort and observations; repeated enrolment does not
  reset an entry deadline. Tampered events and invalid approvals are refused.
- An unavailable durable store prevents the first paid generation.
- Signed endpoint refuses anonymous reads, stale/crossed quotes, synthetic
  datasets and trade authorization; failure never returns a success receipt.
- Restore produces the same report; the ASH-like discovery deferral is reported
  as a coverage miss, not an AI veto or evidence of a profitable trade.

Deployment requires dashboard migration `0006_research_events.sql` and the
signed endpoint first, then the tested backend revision pinned in the main
scheduler. Roll back the workflow revision to pause new comparison writes;
preserve stored evidence. The existing approved-paper journal is still separate.
