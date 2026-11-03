# Generic candidate review connection

The manual scanner workflow can now select one shortlisted stock or crypto
candidate and pass its package through six independent specialist reviews, debate,
and conclusion. No ticker is hardcoded in this path. `candidate_market` chooses
stocks, crypto, or auto (stock-first); the existing shortlist determines rank.
Default remains a zero-model-call dry run. `paid_analysis` explicitly enables one
eight-call review using the existing durable GitHub budget ledger and limits.
There is no paid batch fanout or automatic retry. The old NVDA plan-review
workflow remains available as a separate legacy test path.

Before dispatch, the package is reproduced from the original capture and news at
its assembly time, and checked for current validity. Source IDs, role identity,
all missing evidence and the exact peer sequence are checked after each reply.
Each specialist starts without peer reports. Debate gets six; conclusion gets
seven. Lossless columnar candles reduce repeated keys without dropping evidence.

A review must start before package expiry and finish within ten minutes. Evidence
expiry is never extended: a review that finishes later is STALE_RESEARCH_ONLY.
This is intentionally research without a trade plan. All results forbid trade
authorization, retain unresolved evidence and allow only REJECT,
MORE_EVIDENCE_REQUIRED or RESEARCH_WORTH_FOLLOWING. The last means further
investigation, never entry permission. Native currency remains explicit.

The paid adapter writes an audit before requests, retains returned usage even
when semantic validation rejects a reply, and preserves budget holds on unknown
transport outcomes. Existing day/month/lifetime caps are unchanged. Cost FX is
stored separately and never clears a candidate's missing trade-plan FX evidence.

## Dashboard connection

Optional `send_candidate_review` signs a completed result for the fixed endpoint
`/api/public/candidate-reviews/ingest` on the existing Lovable app. This is separate
from both the capture snapshot and legacy paper-plan archive. Failed delivery
never re-runs the AI. The backend saves `dashboard-archive.json` and delivery
status in the run artifact. UI deployment and actual delivery must be verified
separately; code/tests alone do not prove either.

The `candidate-review-archive-v1` envelope includes exact canonical `package_json`
and `result_json` strings, package/candidate identities, completion and original
expiry, PAID_AI origin, summed estimated cost in micro-EUR, EUR reporting,
`plan: null` and `trade_authorized: false`. Hash the original UTF-8 package_json
string to verify package_id; do not reserialize it in another language. Signature
uses the existing timestamp + dot + raw-body HMAC protocol. Success must echo
SHA256(raw request body) as archive_id. The exporter reconstructs the eight-stage
result and checks its paid usage audit before delivery.

## Verification at implementation

630 local tests passed, including generic equity/crypto reviews, peer isolation,
package reproduction, invalid citations, incomplete roles, stale admission,
expiry during review, review deadline, durable-client requirement, paid audit
preservation, repository/manual-attempt guards, archive signatures and no retries.
These tests use deterministic responses and do not establish live model success.

GitHub verification run 41725680651 also passed. A separate live, zero-model-call
scanner rehearsal (41725919997, commit 77ee88eb76e0c4254bda25b7e06def9c9e1153e0)
completed successfully on 2026-11-03. Its downloaded artifact checksum was
`b12e0811f28748a9e5a41df723358789bd2fe01073c8132422f03c60f16715e8`.
All four requested crypto pairs were rankable, XRPEUR and ETHEUR were shortlisted,
and the runner selected crypto:XRPEUR with state ready_dry_run and model_calls 0.
The eight stock captures were not rankable at this time. No paid review, dashboard
archive delivery or trade is claimed by that dry run.
