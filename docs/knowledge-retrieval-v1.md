# Playbooks and past cases: offline milestone

The scanner now has versioned explanations of its three existing stock strategies and a deterministic historical-case retriever. This is an isolated research input layer. It does not change production approvals, entry rules, orders or alerts. The scheduled preparation worker makes **zero model calls**.

Complete runtime/source checkout: [`9ae20ef`](https://github.com/Chiizzie/market-radar-ai/tree/9ae20ef8454a654fabee488cba9c1fbed9ba664c). The commands and paths below refer to that checkout; main is the workflow/deployment control branch.

## Frozen source and scope

- Training cutoff: **13 November 2026, 21:17:12 Europe/Dublin**.
- Actual library build: **13 November 2026, 21:41:28.972928 Europe/Dublin**. It cannot be used for decisions earlier than that build.
- Validation starts **16 November 2026**, using later data. Friday's history is training evidence, not a forward validation result.
- Library ID: `48672f661769ad1007d321127bf10301b432ceb4caf3934dd509c3642d5e5f76`.
- Frozen library: `knowledge/library-20261113.json`. Source: authenticated append-only comparison events for 12–13 November under quote-quality protocol `eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8`.
- The archive contains 77,041 events; 77,037 were available by the cutoff. Four later events were excluded. One crypto cohort was excluded. All **712 code-qualified stock cohorts** remain: 707 trend-continuation and five opening-continuation cases.

This population does not include every stock rejected by earlier deterministic screening, nor older cases using incompatible quote policies. There are no qualifying pullback/reclaim cases in this frozen population; that strategy receives its playbook and an explicit empty case list. No cases are invented to fill the gap.

| Historical observation | Count |
| --- | ---: |
| Code-only closed simulations | 55 |
| Code-only losses / wins | 40 / 15 |
| Code-only unfilled | 626 |
| Code-only unresolved | 31 |
| AI-reviewed closed simulations | 3 |
| AI-reviewed no action | 14 |
| AI-reviewed unfilled | 14 |
| AI not reviewed / review incomplete | 679 / 2 |

These labels describe historical reference-price simulations, not broker executions. Rejected examples remain counterfactual; unknown/unfilled outcomes are never assigned zero profit. The case sample is not a representative win-rate estimate. Individual call costs remain in the original ledger; historical case P/L does not include AI costs.

## Retrieval and evidence controls

Python replays the original events into disposable SQLite, then builds a compact JSON index. Both event occurrence and server receipt must precede the cutoff; quote receipt is independently checked. Event IDs, partition, sequence and replay are validated. Each case retains the first cohort identity, packet hash, enrolment event hash and both outcome arms. Source journal hashes and cursors allow independent reconstruction.

Matching first requires the same strategy and quote-quality policy. It scores session phase, recent-volume bucket, spread bucket and momentum bucket with fixed weights **4/3/2/1**. Profit/loss, approval status and ticker popularity do not enter scoring or tie-breaking. At most one example per stock/session is returned, with a maximum of **three cases** and **7,200 UTF-8 bytes** including the playbook. Missing features remain unknown. The byte cap is not a token estimate; real calls use the existing token-counting adapter.

Playbooks describe existing rules at source `208f4bf5f9f1f403fb977075f0ea33912f4463b0`, including triggers, invalidation, mandatory inputs and measurement limitations. In particular, rolling VWAP is not full-session VWAP, and recent-bar volume is not time-of-day relative volume. News checks remain mandatory for chart-led strategies even when a fresh positive catalyst is optional. Playbooks do not add a new trading signal.

## Paired comparison

`knowledge_pair` prepares two independent **single-chief shadow reviews**. It is not a comparison against the full eight-call production team. Both arms use the identical current packet, instructions, model, schema, output cap and deterministic gates. Only the knowledge arm receives the retrieved historical reference. Neither sees the other arm's verdict. Pair-hash parity determines call order, and the report retains that order, input hashes, timing, citations and usage.

A historical citation cannot by itself support current approval. Past cases cannot supply missing current evidence or change the plan. Failed, incomplete and late responses remain in the report; a failed first arm stops the pair, with no automatic retry. Such pairs are excluded from completed-pair decision comparisons, but must remain in the attempt/coverage denominator.

`knowledge_shadow` prepares inputs for every supported code-qualified packet on later scans. Its workflow has no provider, model, Telegram, budget-write or order credentials. It writes auditable input bundles and summaries to Actions artifacts. Setting `KNOWLEDGE_SHADOW_ENABLED=false` pauses it independently.

The separate `knowledge_compare --paid` command is implemented for a subsequent live comparison; **it is not scheduled or activated by this milestone**. It chooses one pair without reading outcomes, saves the full eligible cohort, allows at most one pair per Dublin day, uses the existing durable spending ledger and requires €0.15 headroom. Daily/monthly/lifetime caps remain €1/€10/€100. Lost or failed attempts keep their durable marker. Normal per-call reservations and unknown-usage holds apply. Both arms use the existing pinned model; no price/model assumptions were changed.

## Reproduction

Initial real-history export and full regression verification: [run 43512536368](https://github.com/Chiizzie/market-radar-ai/actions/runs/43512536368). Artifact `knowledge-library-43512536368` contains both compressed source journals, the library and summary; ZIP SHA-256 `27b51b95973041a10cabf9dabd4e52231bffea49f36efd9d30f2202434322bc9`. Actions retains this artifact for 30 days; the immutable source events remain in the research store. To recover the exact journals later, read each partition only through its saved `last_source_seq` and write canonical events in sequence order.

With the exported journals in a directory, reproduce the library offline:

```sh
python -m market_radar_ai.agents.knowledge_build --output /path/to/export --built-at 2026-11-13T21:41:28.972928+00:00
python scripts/verify_knowledge_offline.py --output artifacts/knowledge/offline-receipt.json
python -m pytest -q
```

The independently replayed library matched byte-for-byte. The offline receipt exercises all three playbooks with clearly marked synthetic future queries. It proves mechanics and provenance, not decision quality. Local tests cover cutoff leakage, late server receipt, tampering, negative/unfilled/unresolved cases, outcome-independent ranking, input identity, citation validation, late replies, spending limits and duplicate attempts.

## Remaining validation

Later-market paired model decisions, actual token/latency comparisons and properly observed outcomes are still pending. Report completed/incomplete pair counts, decision agreement/disagreement, citation violations, incremental cost and timing before considering any production change. Outcomes require the same later quote stream and explicit unresolved states; do not infer profit improvement from changed verdicts. No claim of improved profitability is made by this release.

Final source verification: [run 43514177316](https://github.com/Chiizzie/market-radar-ai/actions/runs/43514177316), all 1,622 tests and the committed-library check passed. This includes the future metered adapter, with synthetic calls only.

Deployment verification: the **knowledge-shadow job succeeded** in the regular [21:55 scan, run 43514885887](https://github.com/Chiizzie/market-radar-ai/actions/runs/43514885887/job/132194660782). At 21:56:25 Dublin it correctly reported `outside_validation_period`, zero model calls and no trade authorization, then saved artifact `knowledge-shadow-43514885887` (ID 14080970729). This verifies the installed worker and period guard; it is not a fresh-market paired decision or a claim that the entire still-running scan completed. [Deployment receipt](evidence/knowledge-deployment-20261113.json).
