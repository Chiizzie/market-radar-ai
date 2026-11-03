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

633 local tests passed, including generic equity/crypto reviews, peer isolation,
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

## Verified metered integration

Run **41727193991** at commit **a9c98dc83450bf1a77ef782de8bd3c9913080480**
completed a real eight-call review of **crypto:XRPEUR** and confirmed signed
delivery to the published dashboard. Started 2026-11-03 22:03:00.297841, completed
22:03:45.201603 Europe/Dublin; original evidence expiry 22:03:59.228585. Evidence
was current at completion and becomes stale at its original expiry, not when
someone later opens the archive. The entry cutoff was already reached.

- Package: `30a3060f020a144aa0f8edd095a5b8a7d1bf83d26c93c15bc090ca9a020a23de`
- Signed raw-body archive: `56c5db9f611adb24cdcd62810642d99d729ada0c3378ea05fae3b9219acc4146`
- Downloaded artifact 13274347178 SHA256: `5ebc25aa5ced0255e3528b981f675a4c8da0c074fa0b02efdab111d4e2497e04`
- Eight calls; estimated cost **EUR 0.033951**. Shared ledger after run:
  settled EUR 0.638836, held zero, remaining lifetime pilot allowance EUR 0.361164.
- First seven stages MORE_EVIDENCE_REQUIRED; conclusion **REJECT**. No plan,
  authorization, order, paper position, P&L or accuracy result was created.

Downloaded JSON replay exposed Python tuple/list representation differences in
selection reasons. Reproduction now compares canonical wire representations;
the full downloaded result and exact delivered archive hash reproduce without
calling a model. A regression test covers this persistence boundary. Safe audit
diagnostics preserve field/error categories without exposing provider bodies.

Lovable's initial published candidate research implementation used commit
`9bda12ea7cc5ba9e8064e3d4ec89446b86f13702`; it reported 235 passing tests,
clean typecheck/build and validates the exact Python-generated test fixture.
The fixture is parse-only synthetic test data, never inserted as production
research. The public page was observed requiring viewer sign-in after deployment.

Lovable read-only verification confirmed exactly one genuine XRPEUR row, the
exact 26,718-byte signed body and both hashes, and the approved viewer displaying
all eight reports, citations, gaps, cost and original timestamps on the published
app. The record was shown as stale research only; no plan/order/actionability was
present. Sign-out cleared it and reload remained protected; no browser errors
were reported. No synthetic fixture was inserted for this verification.

The original package's NOT_RUN and six_agent_review_not_run are historical input
fields. Eight completed reports are separately present in the result. Prompt
instructions now explicitly forbid describing supplied peer reviews as absent;
the already stored review is retained unchanged as the original model output.
The display-only follow-up `11b08693910c36b9e571548c0dcac64389e8bdcb` labels
these as evidence gaps recorded at package assembly and explains the historical
review-not-run key. Lovable reports 236 passing tests and a clean typecheck;
stored JSON, hashes, verdicts and validation are unchanged. Backend verification
run 41728044689 passed after the persistence-boundary fix (633 tests).
