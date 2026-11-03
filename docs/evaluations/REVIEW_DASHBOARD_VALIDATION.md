# Review dashboard validation — 2026-11-03

The backend now exports `paper-review-dashboard-v1` only after replaying all eight
responses through the current review validator and checking source identity,
blockers, result consistency, cost records and timestamps. Completion at or after
the original plan expiry is rejected. Exports remain historical and unapproved.

Local validation: `python -m pytest -q` completed with **429 passed**.

Lovable project `97051425-8afb-4ea6-bf3e-f6e5fc127ba3`, commit
`52011f57f3c08e0e913fe48f1e16585be2f6f832`, imports the versioned review and
displays all six specialists, debate, conclusion, EUR plan, costs and expiry.
Independent source inspection confirmed checks for bounded review prose,
terminal punctuation, control characters, inline hashes, unique formatted source
IDs, collision-free blocker matching, timestamp ordering and boolean fixture flags.
These are structural checks, not proof of factual or linguistic correctness.

Lovable reports **141 passing tests**, clean type checking and successful preview
build. Its browser check used the explicitly labelled simulated TEST fixture;
reported label-match misses were attributed to uppercase rendering. Those browser
claims were not independently reproduced in this validation pass.

No new paid OpenAI run was started for this milestone. The earlier real paid report
failed the strengthened prose checks and remains excluded from dashboard exports.
The fixture is not a real review or a trade call. No hosted backend connection or
publication is claimed.

Remaining milestones: complete a fresh paid review under the strengthened
validator within the budget policy; validate its real export in Lovable; resolve
the outstanding evidence/eligibility gates; deploy an authenticated read-only
snapshot service and verify the real frontend connection.
