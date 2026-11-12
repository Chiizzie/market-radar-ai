# Broker-paper order management — 12 November 2026

This is an isolated engineering component, not scanner auto-execution or evidence of a profitable strategy. It uses **Alpaca's paper account**. It does not place Trading 212 orders, connect to live Alpaca, or change either scanner's strategy, AI allowance or existing production runtime pin.

## Verification status

- Initial deployment: `8a0d7e787c5a2707a6761044ad90014ff0527a21`.
- Initial GitHub verification: https://github.com/Chiizzie/market-radar-ai/actions/runs/43232188896 — both fault drills and read-only paper connectivity passed.
- At **13:57:10 Europe/Dublin, 12 November**: paper account ACTIVE, USD, trading/account blocks false, **0 open orders, 0 positions**. Regular session closed; next open **14:30 Dublin**, close **21:00 Dublin**.
- Initial 39 fault tests passed remotely. Expanded local suite: **66 tests**, including 30 seeded fill/cancel/restart sequences within one test. Final revision must be checked in GitHub before claiming deployed verification.
- Read-only preflight **does not establish order-submission permission**. A completed broker entry/fill/protection/exit round trip has **not yet been observed**.

## What is implemented

`market_radar_ai.execution` has no model/AI dependency. The durable SQLite journal records immutable intent fingerprints, reserved risk/capital, submission attempts before POST, broker order observations, cumulative fills and prices, broker positions, incidents and terminal reconciliation. It uses WAL, FULL synchronization, an exclusive worker lock, restrictive file permissions and SQLite online backups.

Client order IDs are stable across restarts. The same source event cannot be consumed under a different intent ID. Missing responses and missing lookups remain uncertain; a 404 never licenses an automatic POST retry. An empty/restored-wrong journal cannot silently replay a broker intent already found under that client ID.

The engine manages **long, whole-share, regular-session US equity limit entries with a broker bracket**. Prices are USD; planned-risk reservations are EUR using explicit, timestamped indicative FX. Initial constraints: max €20 planned risk per entry, €40 combined risk, €500 capital per entry, €1,000 total capital, three simultaneous intents. Demo daily losses plus open reserved risk are limited to €40. These are isolated engineering defaults, not a change to scanner/account limits. Costs use an explicitly unverified 40-bps round-trip reserve; realized fees are not available in this first adapter.

Entry gates require a quote no older than five seconds, FX no older than 15 minutes, spread no wider than 20 bps, a fresh broker clock, an active unblocked USD account, sufficient cash (no margin buying power), matching session close and an unexpired source intent. It stops new entries ten minutes before the broker's session close, and at/after 22:00 Dublin. Broker session times handle early closes and timezone changes.

## Failure handling

| Situation | Behavior |
| --- | --- |
| Duplicate signal or worker restart | Reconcile the original client ID; no repeated entry POST |
| Lost entry/exit acknowledgement | Keep an unknown operation and reserved exposure; query before considering any further action |
| Partial bracket entry | Mark unprotected, halt new entries, cancel the remainder/legs, wait for terminal broker states, then flatten only the reconciled filled quantity |
| Missing/rejected/wrong-size stop | Visible incident and the same bounded cancellation/reconciliation/flatten recovery |
| Pending/failed cancellation | No extra sell until the broker confirms terminal order state |
| Stop fills during cancellation | Re-read fills and positions; do not submit a duplicate exit |
| Partial take-profit | Require the stop quantity to match the remaining position |
| Partial manual flatten | Wait while working; retry only a terminal canceled/rejected remainder with a new recorded ID, up to three attempts |
| Stale feed | Block new entry; broker order/position management does not depend on the quote feed |
| Broker/database outage | Halt entry; retain uncertainty and existing native protection; do not claim flat |
| Foreign orders/positions | Halt entry; never liquidate foreign exposure. Unrelated foreign positions do not disable management of our known position |
| Position/fill discrepancy | Halt, report mismatch, and never guess an exit quantity |
| Session deadline | Request cancellation/flatten five minutes before the original session close |
| Already closed session | Report unresolved remaining exposure, preserve protection, and do not queue a next-day exit |
| Entry kill switch | Halt new entries and cancel unfilled entry exposure; retain protection on existing fully filled positions |
| Worker shutdown/explicit flatten | Attempt bounded close/reconciliation; return nonzero if flat cannot be established |

**Partial fills are an explicit limitation:** Alpaca documents that bracket exit legs activate only once the entry is completely filled. The recovery process cannot guarantee uninterrupted protection during a partial fill, network outage, halt or worker failure. This component is not approved for unattended real capital. Stop prices are not guaranteed maximum losses.

REST traffic has a conservative process-wide spacing ceiling; no request automatically retries a POST. This first implementation polls order state. It does not claim streaming latency or production execution SLOs.

## Commands

Use a dedicated paper account and one persistent journal/worker. Keep credentials in a service secret file/environment, never an intent JSON or repository. The supported variables are `ALPACA_API_KEY` and `ALPACA_API_SECRET`; their paper-endpoint acceptance is checked without exposing values.

Read-only connectivity:

```bash
PYTHONPATH=src python -m market_radar_ai.execution.cli preflight --report artifacts/paper-preflight.json
```

Supervised, already-validated paper intent; this command stays running to manage it:

```bash
PYTHONPATH=src python -m market_radar_ai.execution.cli run --paper-orders --intent /secure/intent.json --db /persistent/paper/journal.sqlite3 --report /persistent/paper/status.json
```

Recover/manage existing journal state continuously:

```bash
PYTHONPATH=src python -m market_radar_ai.execution.cli watch --paper-orders --db /persistent/paper/journal.sqlite3 --report /persistent/paper/status.json
```

The `watch` command does not ingest scanner verdicts. Automatic source authentication, fresh execution-price validation and a dedicated signal-consumption integration remain a separate rollout step. Use the `Intent` dataclass schema; a source ID identifies a trusted caller's evidence, not cryptographic authentication.

Read-only status and an online backup while the worker runs:

```bash
python -m market_radar_ai.execution.cli status --report /persistent/paper/status.json
python -m market_radar_ai.execution.cli backup --db /persistent/paper/journal.sqlite3 --backup-to /persistent/backups/paper-unique.sqlite3
```

Backups must use a new destination filename. Recovery requires stopping/fencing the previous worker, restoring a verified backup on persistent storage, and letting the worker reconcile with the same paper account. Never run two restored copies against the account. Broker observations, not local acknowledgement state, determine filled exposure.

`deploy/market-radar-demo.service` is a hardened **host template**, not an installed service. It needs an always-on host, persistent disk, a private environment file, separate backups and operational monitoring. No hosting subscription has been created. A local worker lock is not a distributed account lock.

## Bounded broker exercise

```bash
python -m market_radar_ai.execution.exercise --paper-orders --exercise-id engineering-20261112-v1
```

The engineering fixture uses **one share of F**, only if its fresh quote is between $2 and $30 and the account is otherwise empty. Its fixed limit ceiling is at most five cents above the observed ask (half a percent for lower-priced quotes), rounded down to a whole cent. The $30 ceiling and all spread, freshness and risk gates still apply. This symbol is a small-notional plumbing fixture, not a recommendation or scanner signal. It uses the scanner's existing fresh FX provider. It refuses closed markets and does not substitute extended hours. It requests an exit once active protection is observed, then verifies that the broker has no positions/open orders. It preserves the input, report, journal and recovery backup. The 240-second observation bound can end unresolved; such a result is not success and needs immediate paper recovery investigation.

The GitHub workflow's ordinary pushes run tests and read-only preflight only. A separate order-exercise job is deliberately gated by the exact one-shot commit message `Verify broker paper round trip 2026-11-12`; it must not be triggered until the market is open. Rerunning without restoring the original journal is not a recovery procedure. GitHub Actions is used for this bounded engineering test, **not as the persistent trading service**.

## Remaining acceptance / rollout work

1. Observe the full broker-paper entry → active protection → exit → reconciled-flat evidence on the final code.
2. Deploy a persistent dedicated paper worker, backups and health/incident reporting; exercise process termination and storage/feed/broker outages there.
3. Wire trusted scanner approvals into this isolated demo pipeline and a read-only dashboard status view, with explicit source/price/risk validation.
4. Reconcile execution activities, fees and later corrections; add streaming trade updates with REST recovery before claiming low-latency execution.
5. Continue prospective code-versus-AI strategy evidence separately. Engineering success says nothing about profitability.
6. A future Trading 212 adapter needs its own demo acceptance. The public API's non-idempotent order endpoints and protection/linkage capabilities cannot be inferred from Alpaca behavior.

Sources checked 12 November:
- https://docs.alpaca.markets/us/docs/orders-at-alpaca
- https://docs.alpaca.markets/us/reference/getorderbyclientorderid
- https://docs.alpaca.markets/us/docs/paper-trading
- https://docs.trading212.com/api/orders/placelimitorder
- https://docs.trading212.com/api/section/general-information/api-limitations

## Broker response mapping learned during acceptance

On the third broker exercise, an actual paper entry filled and the engine flattened it after incorrectly treating a `held` stop as missing. The account ended flat. The raw broker group is now a regression fixture with its source run/commit/artifact digest. A held stop is recognized as armed only when the same bracket group has a fully filled entry, a live take-profit sibling, matching remaining quantity and no termination timestamps. Missing group identity, both exits held, partial entry, wrong quantity and cancellation markers still fail closed.

Observation records now use receipt time after the broker response; broker event timestamps remain separate. Earlier artifacts retain their original poll-start observation timestamps and are not rewritten.

Relevant primary references:
- https://docs.alpaca.markets/us/reference/subscribetotradev2sse
- https://forum.alpaca.markets/t/bracket-order-exit-trades-not-executing/3697
