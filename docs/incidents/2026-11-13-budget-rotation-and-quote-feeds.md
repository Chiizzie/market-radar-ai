# 13 November: durable budget rotation and quote-source diagnostics

## Demonstrated problems and scope

The budget ledger reached its 500,000-byte file ceiling while AI allowance remained. Compact JSON restored temporary capacity, but the ledger kept growing. The 18:05 comparison watcher also recorded six stale IEX quote failures for MFG/OCUL despite a maximum polling gap of about 5.74 seconds. These are separate storage and market-data problems.

Hypotheses: (1) moving immutable settled entries behind one compare-and-swap manifest removes repeated growth failures without changing financial accounting; (2) a bounded, contemporaneous IEX/SIP probe can distinguish entitlement and source coverage from a stalled watcher. Neither change changes a strategy, quote freshness/spread gate, model prompt, spending allowance, historical outcome or order permission.

## Storage design

- The **logical ledger stays version 1**. Every existing budget check still receives all identities, receipts, settled charges and unresolved reservations. Daily, monthly and lifetime calculations continue to use the full ledger.
- Physical version 2 contains active entries and a bounded index of immutable settled-record archives. The active root rotates above 240,000 bytes toward 120,000 bytes. Each archive is at most 120,000 bytes, named by its SHA256, with Git blob SHA, byte length and entry count verified on read. The unchanged 500,000-byte root ceiling still fails closed. There is a bounded 512-archive safety limit; this is automatic rotation, not unlimited storage.
- Only settled entries can be archived. Pending/ambiguous holds stay active regardless of age. Historical entries, including zero-cost cooldown identities, are never deleted or overwritten.
- New archives are created first on `state/ai-budget`. They are not spending authority. The existing root-file CAS is the sole financial-state transition. A concurrent winner makes the CAS fail and spending is re-evaluated. An interrupted rotation may leave unused immutable files; it cannot discard a charge or authorize a model call.
- Lost manifest acknowledgements remain ambiguous and block model access. Settlement recovery may confirm an exact recorded receipt read-only. Immutable archive-upload acknowledgements may be verified by reading the exact path and matching bytes; uploads are not blindly repeated.
- A fresh process reconstructs and validates every archive before trusting remaining allowance. Cached archives are immutable; the current root SHA still guards every write. Corruption, missing segments, duplicate identities, incompatible versions and conflicting historical edits fail closed.
- Migration is explicitly enabled for the scheduled reviewer after compatible collector/reviewer/readiness runtime pins are deployed. The maintenance workflow shares the existing budget concurrency group and has no model, market-data or Telegram credentials. A fresh reader must reproduce the exact logical ledger and all period totals after migration.
- Old readers reject physical v2 rather than interpret active-only charges as the complete history. Re-enable any older manual paid workflow only after pinning a compatible reader. Never restore the old file over a live v2 ledger to roll code back; that would remove later transactions.

## Quote-source audit

The audit runs after comparison observation and writes an artifact and job summary. It requests at most eight symbols: SPY as a control plus recent failed symbols. It samples IEX and SIP up to three times, five seconds apart; explicit auth/entitlement/rate refusals stop further requests to that feed in the same audit. Response text and credentials are not logged. Only known subscription refusal codes/phrases are classified as entitlement failures; an arbitrary 403 remains unclassified.

Each quote retains its source timestamp, receipt timestamp, USD bid/ask, age and spread. Future, missing, malformed, crossed, stale and wide quotes remain separate. The existing 30-second freshness and 20-bps comparison reference thresholds are retained for diagnostics. A valid quote from one symbol does not hide another symbol's missing data.

The alternative feed is **diagnostic only**: it never fills the existing paper experiment, rewrites an earlier missed quote, buys a subscription or changes the source policy. IEX and SIP are delivered by the same provider, not independent provider verification. Any source-policy promotion needs a separately frozen prospective comparison.

Official references checked 13 November 2026:

- https://docs.alpaca.markets/us/docs/market-data-faq
- https://docs.alpaca.markets/us/reference/stocklatestquotes-1
- https://docs.github.com/en/rest/repos/contents

## Pre-deployment validation

- Full exact-source offline suite: 1,580 tests passed; compilation and both synthetic protocol rehearsals passed.
- Failure tests include concurrent rotation/reservation, lost write acknowledgements, restart duplicate suppression, unavailable or corrupt archives, pending holds, lifetime accounting across month boundaries, idempotent maintenance, and quote permission/data failures.
- Actual ledger read rehearsal at 18:33:37 Dublin: 1,059 entries, 398,563 logical bytes. Proposed active root 120,286 bytes plus three immutable archives holding 734 settled entries. All six unresolved holds remain active. Reconstructed entries and all spending-period totals matched exactly. This rehearsal made zero remote writes and zero model calls.

## Evidence still required

Verify the compatible runtime deployment, the real maintenance receipt, subsequent scheduled collection/review/readiness reads and the first live quote-source audit. Preserve unresolved source gaps; do not make the workflow green by accepting old quotes. The frozen reviewer-selection and strategy experiments still require later unseen sessions; this storage/data work does not establish profitable performance.

## Deployment validation

The exact runtime `5ca5ffe1354729ddbbb735f8055fd0d50656f6d0` passed GitHub Actions run [43484084327](https://github.com/Chiizzie/market-radar-ai/actions/runs/43484084327), including the full 1,580-test suite and offline fixture checks. Main-branch reader compatibility passed 50 budget tests. The main tree itself still has pre-existing missing `candidate_packages` imports and cannot run its full legacy suite; production jobs use explicit tested runtime pins. This deployment does not present the incomplete main tree as a runnable runtime.

The live read-only rehearsal at 18:33:37 Dublin used ledger blob `6f69b486527b6f9d6b60db886ccdba911017665d`: 398,563 bytes, 1,059 entries. Proposed physical storage: a 120,286-byte root plus three immutable archives holding 734 settled entries; all six unresolved holds remain active. Exact reconstructed state and period accounting matched. The rehearsal made no state writes or model calls. Completed deployment receipts will be appended after the maintenance and natural scheduled runs finish.

## Confirmed production rotation

Deployment commit: `75446426e5cd66dba6f0c6b18e1ff8a7924acd14`. The maintenance workflow [43485117356](https://github.com/Chiizzie/market-radar-ai/actions/runs/43485117356), job `132091720190`, completed successfully. Its report at 18:42:45.612946 Dublin confirms rotation from a 402,298-byte legacy root with 1,069 entries to a 120,590-byte manifest: 314 active entries and 755 settled entries across three immutable archives. All six unresolved reservations were retained. Before and after logical SHA256: `784482969aebe6704087a79350885dccdbd04886dc3f61e0b2c2a44332ec3599`. A separate connector read of the root and all three archives reconstructed that exact digest locally.

Artifact `14067132109` (`budget-storage-43485117356`) SHA256: `e84993f051e32308f7ea8b1e591d6e83c9d5b140fec5d1ded12be8467125a96a`, downloaded and verified. Root blob after rotation: `4a32bffe8ab770366694d7b77ea7044aa69b6912`. Maintenance used no model, broker, or Telegram credentials and made zero model calls.

Execution/readiness workflow [43485117103](https://github.com/Chiizzie/market-radar-ai/actions/runs/43485117103) also completed successfully on the compatible runtime. Signed readiness event `181562`, report as-of 18:43:33.794817 / receipt 18:44:51.429351 Dublin, reads all archived accounting correctly. Eleven operational checks passed and one was blocked: the unchanged daily EUR1 allowance has EUR0.129096 remaining, below the existing EUR0.15 attempt headroom. Lifetime remaining EUR93.710817 and monthly EUR3.710817 do not override the daily cap. Paid review gating is working; routine collection and observation continue.

The evidence helper validated current report schemas and bindings at 18:45:26.486246. Open issues still include broker cost assumptions, incomplete historical AI-cost attribution, unresolved reference exits and future performance validation. Passing storage and operational tests does not establish profitable trading or live readiness.

The first natural post-deployment scan is [43485677181](https://github.com/Chiizzie/market-radar-ai/actions/runs/43485677181), launched at 18:45:18 Dublin. The review log confirms checkout `5ca5ffe1354729ddbbb735f8055fd0d50656f6d0`. Collection, account sync, context and review jobs completed successfully. Snapshot `24054c90a76eb39b5113fbbd3dcb6c2e9eae48ccf61e1361a0f7121492cdbd13` was generated 18:46:07.646573 and received 18:46:09.546783. The review returned `budget_deferred` for BROS at 18:46:59 with zero model calls and the correct unchanged EUR0.129096 daily headroom. A successful deferred job is not a new completed AI review. Observer and feed-audit results are recorded below only after completion.

## Completed natural run and remaining data access

The complete 18:45 run [43485677181](https://github.com/Chiizzie/market-radar-ai/actions/runs/43485677181) finished successfully at 18:53:11 Dublin: all eight jobs passed. The comparison worker recorded 63 polls and 1,257 quotes, with maximum observed inter-poll gap 5.494912 seconds. Three stale BROS quotes formed a 14.857014-second gap that recovered; no quote gaps remained unrecovered. Startup synchronization took 16.832216 seconds and remains a warning. This single completed run does not prove sustained data coverage.

The separate feed audit ran 18:51:17.893538–18:51:28.152953. IEX returned six SPY/BROS observations: four passed the diagnostic age/spread limits and two BROS observations had spreads around 39.77 and 36.94 bps, above the unchanged 20 bps gate. SIP returned one HTTP403 and subsequent requests were skipped. The first audit conservatively classified it as `forbidden_unclassified`; no delayed quote or alternate feed entered the frozen experiments.

Comparison artifact `14066914123`, SHA256 `93597b86ef86a063f0c00f3415693672b6e6b22a6242efd370b89b4bc33ac907`, was downloaded and verified. It contains `worker-health.json`, `quote-source-report.json`, and the decision comparison. The latter, as of 18:51:08.237194, traces 208 cohorts; four new-prompt review cases remain unfilled in all three selection arms. Matched closed comparisons: zero. Existing team-call cost EUR0.197178 and chief-call cost EUR0.023386 are attribution to existing calls, not added diagnostic calls or proof of standalone-chief strategy performance.

To identify the 403 without exposing arbitrary provider text, commit `a913bb2efd7b2db55fb892bf2d9f22c6d1e8bb8c` updated the existing manually/push-triggered quote-audit workflow to make exactly one current SIP request. Run [43486974990](https://github.com/Chiizzie/market-radar-ai/actions/runs/43486974990), job `132097895471`, completed successfully. At 18:53:39.668151 it recorded HTTP403, no numeric provider code, and `subscription_restriction_reported: true`. This flag means the provider error message mentioned a subscription; its raw text was not retained. SIP remains inaccessible with the deployed credentials. Artifact `14067393212`, SHA256 `ae5ce783f8523d7b4dadb50416529288af5117298a0076223edc5c449116b25c`, was downloaded and verified.

Alpaca's [official plan documentation](https://docs.alpaca.markets/us/docs/about-market-data-api), checked 13 November 2026, lists Basic real-time coverage as IEX and Algo Trader Plus as all US exchanges at USD99/month. No subscription was purchased or changed. An access/plan decision is required before proposing a separate prospective consolidated-feed experiment. Do not represent a paid feed as a guarantee of better strategy returns.

### Completion boundaries

- Done: tested archive implementation, automatic rotation enabled, live migration verified independently, compatible readers deployed, scheduled delivery verified, bounded recurrent quote diagnostics deployed, provider refusal investigated.
- Still open: broad real-time quote access/coverage; sustained operational evidence; future-session strategy and reviewer-value validation; actual broker costs and eventual order-engine readiness.
- Current operational constraint: paid review attempts are deferred under the existing EUR1 daily cap; collection/observation continue. No allowance, historical record, strategy/quote gate or live-order permission changed.
- Main source cleanup remains separate technical debt: legacy main has missing modules, while actual production jobs use the explicitly verified runtime. Never deploy an untested main checkout as the whole scanner.
