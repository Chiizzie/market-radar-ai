# Paper plan review contract v1

`agents.plan_review.prepare(capture, catalogue, draft)` reproduces the deterministic EUR draft from its original Alpaca capture, catalogue and FX at evaluation time, compares all plan fields and blockers, and returns canonical JSON. Each source has a hash identifier; the full packet has a digest. These are integrity identifiers, not proof of provider authentication.

`run(packet_json, ask, clock=...)` checks packet reproduction, invokes six independent role responses without peer output, then debate with six reports and conclusion with those reports plus debate. It rejects expired plans before and after calls, wrong packet/stage/citation identities, missing blockers and missing peer acknowledgements. Any verdict remains unapproved. Free-text reasoning is not automatically proven factual by schema validation. Contradictions are available to debate; semantic resolution is not deterministically guaranteed.

`run_paid` is an explicit opt-in adapter requiring the existing OpenAIPilot and durable GitHubSpendingLedger. It uses deterministic request identifiers, bounded output, and writes a report before calls and records returned usage before semantic validation. Failure stops rather than retrying. This adapter has not yet had a credentialed live plan-review trial. No workflow enables it automatically. The eight added tests verify orchestration with controlled responses and rejection of altered plans, expired plans, fabricated citations, cleared blockers and unsupported paid clients; they are not real AI performance results.

Next: wire a manual fresh-capture workflow to this adapter, validate its paid audit behavior with the durable ledger, and run one bounded trial before surfacing actual agent reports. The prior successful research-only AI run does not validate this new plan-review contract.

## Dashboard delivery

The existing Lovable project already supports historical snapshot import. An update was requested to accept raw eur-paper-draft-v2 JSON as an unapproved draft, show EUR levels/assumptions/blockers, preserve original expiry and label plan review not run. Never promote imported drafts to actionable status. Automatic updates still require a deployed authenticated read-only endpoint; local import is not that endpoint.

Validation: 409 local tests passed. The additional paid-adapter test uses mocked client/ledger types to prove returned usage is retained after a fabricated citation is rejected; this is not a live billing trial.

Historical real NVDA import document: docs/dashboard/nvda-paper-draft-2026-11-03.json. Original expiry is preserved.
