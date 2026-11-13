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
