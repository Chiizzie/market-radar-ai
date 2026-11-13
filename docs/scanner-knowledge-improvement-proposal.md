# Scanner knowledge improvement proposal — 13 November 2026

Status: proposed research and integration scope, not installed skills, deployed reviewer changes, or a validated trading improvement.

## Current implementation checked

The current workflow still pins collection/review/comparison to 208f4bf5f9f1f403fb977075f0ea33912f4463b0. The paid-review instructions have six specialist roles plus debate/chief stages, policy paper-specialists-v3-conditional-chief and prompt revision paper-compact-evidence-20261113-v2.

The reviewed path in agents/paper_review_prompts.py, agents/candidate_packages.py and agents/paper_verdict.py uses bounded candidate-specific source packets. It already has strategy-specific conditions, news relevance/freshness instructions, earnings-calendar caveats, immutable decisions and outcomes. It does not retrieve a curated historical case library for the reviewers. Personal assistant skills and ChatGPT connectors are not automatically available to scheduled Python jobs.

Existing strategy, context and entry experiments should be extended through an explicit versioned experiment; do not add new names for already-existing roles or relabel generic model confidence as a calibrated probability.

## Recommended first milestone: playbooks plus evidence-backed case retrieval

1. Represent each existing supported setup as a versioned guide: necessary inputs, conditional entry trigger, invalidation, known failure modes, missing-data behavior and source references. Keep trading arithmetic and hard gates in code.
2. Build a case index from immutable source events. Separate approved/observed trades, rejected hypothetical setups, unfilled plans, unresolved outcomes and provider/storage incidents. Include losses and unsuccessful examples.
3. Retrieve a small deterministic selection using setup, session phase, observed participation/liquidity and available market context. Do not rank solely by later P/L, ticker familiarity or attractive screenshots. Small samples remain explicitly insufficient.
4. Bind every retrieved document/case to a source digest, version and availability time. For historical replay, both inputs and any outcome label must have been available before that simulated decision. Freeze the training/reference cutoff before later validation sessions.
5. Attach only the relevant short extracts to a new candidate-packet/prompt experiment, recording the retrieval manifest, latency and model cost. Initial indexing, retrieval and fixtures can be built and tested offline without paid model calls. Existing EUR allowances remain unchanged.

Acceptance: deterministic retrieval and complete provenance; no future-dated cases; all losses/missing exits retained; known bad cases do not become valid because of similar prior winners; compact packets; paired evaluation against the existing reviewer path on the same later eligible setups. Track factual errors, invalid approvals, missed eligible setups, decisions completed before expiry, costs and eventual after-cost outcomes. Development examples are not unseen validation.

## Further additions

| Addition | Proposed integration | Evidence needed |
| --- | --- | --- |
| Primary-source catalysts | Link issuer announcements and SEC filings to the exact company; deduplicate repeats; distinguish publication, event and ingestion times, guidance changes and rumours | Correct company/date/source fixtures; actual usable availability before the decision; retrieval failure remains unknown |
| Market and sector context | Bring measured broad-market/sector-relative behavior into the candidate packet, using existing context work where applicable | Inputs genuinely available at the decision; no invented relative strength; a separately frozen comparison for changed strategy routing |
| Company reference knowledge | Dated identity, sector, verified relationships, earnings/event references and broker/instrument mapping | Auditable sources, expiry/update rules, corporate-action/identity handling; no unverified relationship turned into a catalyst |
| Decision calibration | Evaluate with and without the added knowledge; retain costs, latency, unresolved cases and clustered same-day outcomes | Later chronological validation and uncertainty by session/regime; no automatic promotion from a fixed trade count |

## External material checked

- Alpaca official backtest skill: https://github.com/alpacahq/alpaca-skills/blob/main/skills/trading-api/backtest/SKILL.md — useful reproducible research workflow. Use the earlier fixed-revision audit in skill-catalogue-review-2026-11-12.md as context, then re-review the exact package/references/CLI version before adaptation. Intraday quote freshness, limit-respecting fills and point-in-time rules must be explicit. No installation occurred.
- OpenAI official CI/security skills: https://github.com/openai/skills/tree/main/skills/.curated — useful engineering support, not a source of demonstrated trading edge. The current scanner audit already covers scheduled-run incidents.
- SEC primary data: https://www.sec.gov/search-filings/edgar-application-programming-interfaces and https://www.sec.gov/about/developer-resources — submissions and company financial facts can be retrieved programmatically. Respect published access rules and retain original document/timestamp provenance. Financial statements alone do not establish an intraday catalyst.

No new external service, secret access, paid subscription, broker order, AI allowance or automatic strategy adjustment is introduced by this proposal. The remaining IEX freshness/coverage limitation needs its own evidence; knowledge retrieval cannot substitute for observed executable prices.

