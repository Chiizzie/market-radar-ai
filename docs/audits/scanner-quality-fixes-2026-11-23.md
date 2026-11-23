# Knowledge-input and manual-cost repair — 23 November 2026

Follow-up to the [evidence-led quality audit](scanner-quality-2026-11-23.md). All times are Europe/Dublin.

## Completed implementation

The knowledge worker previously requalified a collector artifact at its later startup clock. That discarded original valid inputs when their quotes became stale. It now reproduces the complete original packet set at the recorded packet-qualification clock and requires exact canonical equality. It retains that source clock and hashes separately from the real processing clock. Missing, altered, future or unreproducible input fails closed.

These are explicitly offline preparation records. The paid paired-review adapter refuses them, even while the original plan has time left. A paid/live comparison still needs new preparation and its normal freshness checks. No model call or decision is backdated, and the paid knowledge comparison remains inactive.

The same existing artifact now includes `manual-feasibility.json`. It uses the existing execution-research sizing/fee functions with the owner's confirmed EUR-conversion route, original stops and targets, and unchanged €500 allocation / €20 research risk caps. It records itemised assumptions, cost rejection reasons, original expiry and the latest possible notification times for 60/180/300-second responses. It does not invent an acknowledgement, a fill or a response-qualified outcome. Current fee and slippage assumptions remain unverified as a complete broker execution model. It is diagnostic; ordinary alerts and paid review admission are unchanged.

## Evidence and tests

- Exact runtime base: `9ae20ef8454a654fabee488cba9c1fbed9ba664c`; four-file runtime patch: `2589990ab537c527ee97c5c6ba410336aafea914`. Only the knowledge job's runtime pin changes.
- The original [20:30 ordinary run](https://github.com/Chiizzie/market-radar-ai/actions/runs/45260077746) contains 30 packets stamped **20:31:30.358712**. Its separate earlier qualification file and its packet qualification clock are not interchangeable.
- Offline processing at **21:40:57.359435** reproduced all 30 packets and prepared all 30 pairs without changing original inputs. Actual source age was 4,167.000723 seconds; live review readiness remained false. The original worker had prepared zero after startup.
- All 30 original plans fell below 2R under the existing itemised EUR-conversion/worst-allowed-entry assumptions. This is cost feasibility on already-qualified packets, not trading performance, and does not establish a profitable alternative.
- Main source suite: **2,142 passed, 22 subtests passed**. Exact patched runtime suite: **1,634 passed**. Added cases cover delayed processing, immutable clocks and inputs, future/tampered/incomplete input, future knowledge leakage, paid-adapter rejection, unchanged targets/caps and missing actual notification evidence.
- GitHub PR checks and post-deployment ordinary-run verification are recorded on the implementation PR. Saved-input reproduction is not a substitute for that deployment check.

## Remaining acceptance gates

Cost-aware admission before paid review requires a separately versioned controlled comparison and validated cost assumptions; it is not silently enabled here. The existing fresh-breakout comparison still needs genuine later 1/3/5-minute observations and closed outcomes. Coverage recovery, unresolved historical exposure and intake backlog remain as documented in the audit. No profitability gate is closed by this repair.

## Bounded performance-intake follow-up

The performance workflow now also listens for completed ordinary main scans. Only the first five-minute dispatch slot of each hour is eligible, the original parent must be less than 20 minutes old, and the existing Dublin weekday window applies. Forks, branches, retries and cancelled parents are excluded. A partially failed ordinary scan may still contribute saved evidence.

The existing hourly timer remains a fallback. A bounded read checks for an actual, unexpired performance artifact from a successful run completed within 45 minutes, avoiding duplicate reconstructions. A green window-only job, missing/expired artifact or failed GitHub read cannot suppress intake. The artifact reader, append-only evidence bank, frozen portfolio replay, costs and strategy rules are unchanged; no trading/provider/model credentials are added.

Tests execute the real workflow window script against normal/late/future parents, duplicate and expired receipts, GitHub timeout, weekend and summer Dublin clocks. The report-window and artifact-reader suite passed **33 tests**. Completion and backlog reduction must be verified from the next saved output; configuring a trigger does not establish a fresh source cutoff or complete outcomes.
