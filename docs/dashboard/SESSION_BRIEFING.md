# Whole-universe session briefing v1

Implemented preparation runs without the momentum strategy's twenty completed five-minute bars. Weekdays only, beginning 08:00 Europe/Dublin: one morning review; one preopen review from 08:30 America/New_York; one opening review from 09:30 to 10:00 America/New_York. These are clock phases, not a verified exchange holiday calendar. Data continues collecting between reviews. Budget and existing quotas remain enforced; a scheduled tick may be deferred.

Six independent specialists, debate and final conclusion each return one symbol_decision for every covered stock, with WATCHLIST, AVOID or MORE_EVIDENCE_REQUIRED, rationale, opening_condition, invalidation and scoped source_ids. Requested but unavailable symbols remain explicit. No fixed 16:10 gate applies to preparation. The later momentum strategy retains its bar requirement.

New envelope: session-briefing-archive-v1. Same signed ingest fields and archive hashing as candidate-review-archive-v2. package_json contains the {package_id, package} wrapper using session-evidence-package-v1. result_json uses session-briefing-result-v1. The package is reconstructed and all eight responses are replay-validated before export. The response adds symbol_decisions to the existing CandidateReview format. See session_briefing.py and test_session_briefing.py for exact contract and fixtures.

Historical native USD levels remain labelled historical; EUR conversion is not supplied. Evidence expires within five minutes. CURRENT_CONTEXT_ONLY never means executable prices. trade_authorized is false and plan null throughout. Brokerage eligibility, current quotes/costs, EUR sizing and execution admission remain separate requirements. This is research preparation, not an approved trade.

Validation: 831 local tests passed on 2026-11-04. Dashboard parser/deployment and production scheduler pin must be updated before enabling delivery of this new envelope. No live session briefing has yet been verified. Existing daily/monthly/lifetime AI caps have not been increased.
