# Timestamp replay incident — 9 November 2026

At 08:16 Dublin, report event 178 was stored with an original timestamp ending .964140+00:00. PostgreSQL TIMESTAMPTZ output shortened its fraction to .96414, invalidating the byte-based event checksum during replay. This blocked subsequent paper comparisons and execution/readiness reports. Collection and account syncing continued in inspected runs.

Repair: reconstruct the producer's UTC ISO timestamp at the shared EventClient read boundary, accepting it only if the unchanged event hash matches. Preserve payloads, identities, partitions, ordering and downstream validation. Do not delete or overwrite historical evidence. Apply the same narrow patch separately to the currently pinned scanner, execution and method versions; no unrelated feature upgrade.

Validation: 56 focused tests passed, covering trailing-zero precision, no fraction, unchanged timestamps, and rejection of payload/kind/hash/time tampering. Replayed the actual database report records 167, 172 and 178 offline, preserving all hashes and payloads. The scanner's existing pinned source was additionally checked with 43 focused tests, all passing (overlapping coverage; not 99 unique tests).

## Production verification

- Execution/readiness run https://github.com/Chiizzie/market-radar-ai/actions/runs/42595340293 succeeded; all three stored comparison events restored, zero AI calls.
- Comparison storage verification https://github.com/Chiizzie/market-radar-ai/actions/runs/42595766984 succeeded: four real report events, idempotent insert, independent replay and uploaded recovery receipt verified.
- Method storage verification https://github.com/Chiizzie/market-radar-ai/actions/runs/42595766937 succeeded: real empty-cohort report, independent replay and uploaded recovery receipt verified.
- Scheduled scanner https://github.com/Chiizzie/market-radar-ai/actions/runs/42595814410 (09:45 Dublin) completed successfully at approximately 09:51. Watcher: 66 polls, 66 comparison polls, zero error polls, no report/storage gap. Collection, account syncing and review completed successfully; review found no qualifying candidate and made zero paid calls. Stock method/context jobs were outside their active session; their successful job statuses do not demonstrate live-session analysis.

No historical evidence was deleted or rewritten. No active paper plans were present during verification, so this proves the storage/replay repair and idle monitoring, not profitable trades or loaded trade-lifecycle performance.
