# Execution history replay capacity — 13 November 2026

Failure inspected: execution/readiness run 43496441892, job 132130666653.
Both publishers raised `execution_source_capacity`; upload then had no report.
The last stored execution/readiness reports were 19:15:01 / 19:15:15 Dublin.
This predates the new entry experiment and is independent of its deployment.

Cause: collect() accumulated every validated event across days into memory,
reading each daily journal wholesale, then rejected total raw journals >50 MB.
At 20:03 the guarded source contained >61,000 quotes plus 628 enrolments across
12–13 November. Event envelopes add substantially to their payload bytes.

Repair: store every validated event in a temporary SQLite archive. Iterate in
source order for hashing/export and stable sequence order for replay. Preserve
all event payloads, original timestamps, duplicates/order semantics, protocol IDs,
cohorts, fees, exposures and unresolved reservations. The canonical array hash
matches the former list hash exactly. Source gzip restore and the separate daily
trade evaluator use the archive too; the daily validator remains bounded.
No history deletion, cap reset, outcome change, AI call or order is involved.
Readiness timestamps are captured after source reads, so a slow replay does not
stamp new probes with an old clock.

Bounds remain explicit: 1 GB canonical source bytes, one million events, existing
daily validator/page limits and workflow timeout. Crossing a limit still fails
closed. This removes the immediate 50 MB ceiling and whole-history memory copy;
it does not promise unlimited history. Further checkpointing will be needed
before those bounds or replay-time limits are reached.

Verification: synthetic disk/list exact replay, stable ordering, Unicode source
hash, duplicate sequence semantics, >52.5 MB archive/gzip restore, cleanup and
failure before adding an over-capacity event. The real artifact 14069761934 from
run 43490186621 (ZIP SHA256 8ed46bb32a916d36c0fa4c78c39904d6a1d795d4ae5024a882d04336371c58f8)
contained 49,420 events / 49,370,568 canonical bytes. New replay reproduced the
ENTIRE original execution report, all six books, source hash and trade-evaluation
report exactly. See evidence/2026-11-13-execution-disk-replay.json.

Deploy only the execution/readiness job to the new tested runtime. Other scanner
runtime pins and the separate entry-confirmation worker remain unchanged.
