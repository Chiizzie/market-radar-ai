# Timestamp replay incident — 9 November 2026

At 08:16 Dublin, report event 178 was stored with an original timestamp ending .964140+00:00. PostgreSQL TIMESTAMPTZ output shortened its fraction to .96414, invalidating the byte-based event checksum during replay. This blocked subsequent paper comparisons and execution/readiness reports. Collection and account syncing continued in inspected runs.

Repair: reconstruct the producer's UTC ISO timestamp at the shared EventClient read boundary, accepting it only if the unchanged event hash matches. Preserve payloads, identities, partitions, ordering and downstream validation. Do not delete or overwrite historical evidence. Apply the same narrow patch separately to the currently pinned scanner, execution and method versions; no unrelated feature upgrade.

Validation: 56 focused tests passed, covering trailing-zero precision, no fraction, unchanged timestamps, and rejection of payload/kind/hash/time tampering. Replayed the actual database report records 167, 172 and 178 offline, preserving all hashes and payloads. Production verification follows the deployment of the workflow pins.
