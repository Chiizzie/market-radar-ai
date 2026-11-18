# Historical intelligence and prospective validation

Declared 18 November 2026, Europe/Dublin. This implementation reads existing paper evidence; it cannot send an alert, spend model credits, place an order or change a live strategy.

## Milestone ledger

| Milestone | Implemented evidence | Remaining constraint |
|---|---|---|
| 1. Audit | [PR #19](https://github.com/Chiizzie/market-radar-ai/pull/19), merged as `d726e6347d59d43b4be83b832f8731536418e732`; actual failure logs, receipts, source digests, experiments and outcomes | Provider root cause of the 17 November storage outage is still unproven |
| 2. Reliability and completeness | Restored 250 exact deployed source/test blobs; CI now passes; workflow-entry-point completeness regression; verified live observer checkpoint; additive artifact recovery; strict source/clock/duplicate checks | Historic missing quotes/receipts cannot be invented; unresolved records remain exceptions |
| 3. Historical intelligence | All 1,101 current-protocol setups and 127,984 events replayed; full indexed lifecycle, original/refreshed packet identities, alert clocks, rejects, entries, exits, stop/target reasons, costs and unresolved outcomes; EUR expectancy, profit factor, realized drawdown and causal condition splits | Upstream capture backfill is bounded and resumes automatically; earlier protocol versions must remain separate |
| 4. Controlled experiments | Existing ten volume/risk/cost variants and paired entry experiment replayed without changing their protocols; full arm totals and common-subset exclusions; AI-versus-code comparison; one frozen secondary SPY-regime policy comparison | No improvement is established; matched closed subsets are coverage-selected, not randomized trials |
| 5. Prospective validation | Declared holdout begins **19 November 2026**, with a blocking evidence gate and no automatic promotion | Requires later unseen sessions, verified broker costs, adequate coverage and outcomes; cannot be completed by coding today |

## What the verified historical sample says

The original independent setup allocations have 78 closed code-only outcomes, net **−€163.109412**, and seven closed AI-reviewed outcomes, net **−€22.985947**. They also have 53 and four unresolved outcomes respectively. These overlapping fictional allocations are **not** the return of a €1,000 portfolio. The original flat cost assumption applies; AI cost is separate.

The six shared-capital alternatives reproduce the published execution report exactly. USD-balance code has one close, −€4.376654; AI has three closes, −€4.422799. Each still has one unresolved reservation. The EUR conversion and stressed alternatives have no closed trades and are mainly blocked by costs. Missing or unfilled trades are not zero-P/L executions.

The separate manual ledger also reproduces exactly. Its primary stays **EUR conversion / 300 seconds**, matching the conservative end of the declared 1–5 minute response range. All 27 notified setups are blocked in that primary. The USD / 60-second sensitivity has one observed close at −€3.057574 and one unresolved position. It is not selected as a new primary because it looks less restrictive.

There are 74 recorded review attempts, 1,027 unattempted setups, two incomplete cost settlements and €3.456410 in recorded model-cost estimates. Four approved setups lack a matching acknowledgement clock in the available exports. The report distinguishes these from 1,027 unattempted reviews, rather than describing all of them as missing paid usage.

The 65 exception rows comprise 57 unresolved independent-arm outcomes, two shared-book reservations, two incomplete cost settlements and four missing clocks. Arms can overlap; this is not a count of real brokerage positions. No historical alert is resent and no missing exit is fabricated.

Machine-readable evidence: [performance-intelligence-20261118.json](../evidence/performance-intelligence-20261118.json). Source runs: [execution 44327854314](https://github.com/Chiizzie/market-radar-ai/actions/runs/44327854314) and [manual 44330110361](https://github.com/Chiizzie/market-radar-ai/actions/runs/44330110361). The manual source has a distinct evaluation cutoff and later publication timestamp; replay uses the evaluation cutoff.

## Reproduction and outputs

Use the existing execution and manual artifact directories, preserving their report, source export and manual ledger files:

```bash
EXECUTION_SOURCE_VERSION=guarded-v2 python -m market_radar_ai.agents.performance_intelligence \
  --execution /path/to/execution-artifact \
  --manual /path/to/manual-artifact \
  --contexts /path/to/contexts.json \
  --output /path/to/new-output-directory
```

`--manual` and `--contexts` are optional; missing evidence stays explicitly unavailable. The output directory must be new. `performance.sqlite` is a disposable indexed projection containing the exact immutable source export, setup identities, original USD/EUR plans, outcomes, portfolio rows and exceptions. It is not a competing trading ledger. `performance.json` and `performance.md` provide the derived report. Original sources and outcomes are unchanged.

The real 127,984-event execution export plus the separate manual export replayed in **83.67 seconds**, peak RSS **226,684 KiB**, on the development host. Disk indexes page source history; exact-fill diagnostics retain only relevant fill observations. Context reports are checked once and joined by proven availability time, with no future context or missing-data substitution.

## Automated intake

`.github/workflows/performance-intelligence.yml` runs hourly on weekdays in the 08:00–23:59 Dublin window, with an explicit dispatch and deployment verification trigger. It is independent of the live scanner. Its only credential is GitHub's read token; it receives no model, provider, Telegram, ingestion or broker credentials.

- Read completed main-branch artifacts, including failed scanner attempts. A green run without an artifact is not accepted as performance evidence.
- Reuse original discovery selection, qualification, packet and diagnostic files. Keep all discovery states, including unexamined/deferred candidates; group identical states compactly and retain exact qualified candidates and packet links. A tested capture contained 5,723 discovery observations and 30 qualification observations.
- Maintain an additive compressed index, verify hashes on reads, reject conflicting duplicates and recover the preceding completed bank even if later analysis failed. Never silently reset an expired bank.
- Inventory the current protocol's retained history from 12 November. Index at most 120 new candidate/context artifacts and inspect at most 20 frozen-experiment artifacts per invocation. Pending IDs remain visible and subsequent hourly runs resume. Missing/expired files remain gaps, not fabricated histories.
- Reproduce each frozen experiment's aggregates against its full journal. Select the latest report **per protocol and day**, never sum repeated cumulative snapshots. Preserve all alternative arms and exclusion counts.
- Publish the research outputs and bank as GitHub artifacts retained for 90 days. Each new bank carries the prior indexed history forward. This does not replace the authoritative durable research journal. Loss or expiry of the last available bank is a blocking recovery issue.

New analytics make no extra research-database reads and no paid provider/model calls. Existing live workflow files, source pins, alert cadence, broker execution, spend limits and risk settings are unchanged.

## Frozen prospective gate

Protocol file: [performance-holdout-20261118.json](../../config/research/performance-holdout-20261118.json). Its content hash is checked in code. Primary manual protocol and scenario remain unchanged; older positions/reservations carry forward rather than resetting the capital history.

The 100-close / 20-exit-day thresholds are screening checkpoints, not a power calculation or proof of edge. The exploratory day-cluster interval must support positive net expectancy, costs must be verified, end-to-end evidence complete and exposure reconciled. Even then the result only becomes eligible for independent review; it never enables trading.

The secondary regime experiment compares the first enrolled stock setup per Dublin day under the original plan against an up-only policy using a previously available, complete SPY session return of at least +0.3%. A no-action allocation is a negative control. Unknown context/outcomes are excluded with counts; before 19 November is labelled training diagnostic. No live regime filter is enabled.

Important open constraints: actual broker currency route and fee/slippage evidence are unverified; source cost schedules have frozen expiry dates (the execution/manual schedule expires 8 December). Renewed cost evidence requires an explicit new version, never extending or rewriting the historical protocol silently. Archive capacity is reported with a 70% warning. The prior hosting incident, observation gaps, missing acknowledgements and future sample size remain tracked blockers.
