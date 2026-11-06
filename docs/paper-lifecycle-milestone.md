# Observed paper lifecycle

This release addresses the mismatch between 30–60 second approved entry windows
and a five-minute research collector. It does not change strategy qualification,
the EUR 20 planned-risk cap, model spending, broker eligibility, or live-order scope.

## Runtime

- A separate `paper-watcher` job targets a quote poll every five seconds for
  already-approved plans. Each normal weekday dispatch runs for 330 seconds,
  deliberately overlapping the next five-minute dispatch. There is no shared
  concurrency lock with the paid review job.
- Approval first registers its immutable decision, immediately polls references,
  then bridges the entire short entry window with a 65-second watcher. The
  independent watcher continues observing open simulations after review finishes.
- Alpaca IEX stock quotes retain exchange timestamps and are converted with
  validated indicative USD/EUR FX. Kraken references retain local receipt times.
  These are research venue references, not Trading 212/Robinhood executable prices.
- In the final 30 seconds before `exit_by`, the first observed bid closes an open
  simulation. No new entry is allowed in this exit window. A quote after the
  cutoff cannot invent an intraday exit. Missing evidence remains unresolved.
- The paper journal keeps decision-changing observations: entry, pre-entry
  invalidation/risk rejection, and exit. An unchanged poll does not create a Git
  commit. Counts mean retained observations, not every quote received.
- GitHub state is refreshed every 15 seconds. A state change merges against the
  latest CAS head, retrying only definite conflicts. Ambiguous writes are read
  back on the next poll; they never reset history or trigger paid reviews.
- Telegram sends at most one persisted paper-entry notice, one result notice,
  or an unresolved-exit notice per plan/state, using the existing durable delivery
  ledger. An uncertain Telegram acknowledgement is not retried automatically.
- The dashboard receives journal results on the existing capture cadence. Its
  summary includes only closed observed paper outcomes, excluding open/unfilled/
  unresolved plans. This does not turn the scanner feed into a streaming feed.

`PAPER_WATCHER_ENABLED=false` disables the independent watcher and stops new
scheduled paid paper reviews before any model call. Collection/account sync remain
separate. No watcher receives model credentials, uses an order endpoint or runs on
weekends. The watcher stops at 23:00 Dublin; entries/exits still obey their earlier
plan deadlines and the 22:00 latest cutoff.

## Operational evidence

Each run uploads `paper-watcher-<run-id>` with `watcher-health.json` and the latest
paper journal report. Health includes successful/error polls, quote counts,
maximum interval within that worker, and unconfirmed notifications. Runner delays
and provider outages can still cause observation gaps: five seconds is a target,
not a guaranteed exchange tick history. Future persistent hosting/streaming and
database archival remain separate improvements.

The provider smoke check only verifies a current Kraken EUR reference; it creates
no plan, no paper entry, no AI request and no Telegram message.

## Verification

Offline tests exercise real qualification/packet construction, eight synthetic
model responses, fresh revalidation, persistent journal registration, the actual
reference observer, five-second entry, restart/overlap, observed target/stop gap/
scheduled exit, missing exit, and notification acknowledgement. Synthetic results
are never written to the production journal or dashboard.

```sh
python -m pytest -q
python -m compileall -q src tests
python -m market_radar_ai.agents.paper_observer --verify-crypto
```

Passing these tests and provider checks establishes engineering readiness. A
naturally qualified, AI-approved setup followed by recorded market observations is
still required for the first genuine forward paper outcome. Neither synthetic
outcomes nor successful workflow counts establish profitability.

## Continuation checkpoint — 6 November 2026

The agreed milestone is **an approved paper watch followed by an observed entry
and an observed stop, target or scheduled exit**, with expired unfilled plans and
missing exits reported honestly. Engineering readiness is verified; the first
genuine forward paper outcome is still pending.

The implementation is on `phase-1/market-data-layer`. Production's scheduler is
on `main` and explicitly checks out tested backend
`f26f122b69a3be8cba5393a0a011fc3967e53172`; the deployment commit is
`2fbf88a0c95e7c72bdc32a7c58de095c30f405ce`. Reading only the older source files
on `main` does not show the deployed implementation. Do not replace these pins
with the superseded morning-preparation draft PR.

Verified evidence:

| Check | Observed result |
| --- | --- |
| [Backend CI 42215269210](https://github.com/Chiizzie/market-radar-ai/actions/runs/42215269210) | 1,061 tests passed; compilation, offline scenarios and budget-storage check succeeded. Paid evaluation steps were skipped. |
| [Production run 42216881068](https://github.com/Chiizzie/market-radar-ai/actions/runs/42216881068) | Collection, review gating, paper watcher and private account sync all succeeded. |
| Watcher, 12:20:40–12:26:10 Europe/Dublin | 66 polls; maximum interval 5 seconds; zero error polls; zero unconfirmed notifications; zero active plans and zero observed trade quotes. This verifies an idle watcher, not an executed lifecycle. |
| Provider smoke check | Current Kraken XBTEUR reference verified at 12:20:40 Dublin, using local receipt time. No plan or entry was created. |
| Review at 12:22:16 Dublin | `no_qualified_candidate_zero_cost`; zero model calls. Nine requested stocks had no usable regular-session evidence during premarket. All four crypto candidates lacked current symbol-linked news; ETH/XRP also failed relative volume, and BTC failed relative volume and momentum. |
| Crypto reference and catalogue checks | All four candidates passed paper catalogue availability, reference quote, EUR pricing and session checks. The old statement that crypto catalogue integration is absent is superseded by the deployed code and `SCANNER_COVERAGE.md`. Live account permission and broker execution prices remain unknown. |
| Durable production journal | `state/paper-journal` contains zero decisions and zero observations (blob `783be593209c8016221ed08469a539c265d989af`). No genuine paper result or performance statistic exists yet. |

The downloaded decision artifact `13502161496` was independently checked against
SHA-256 `9798189e9d052e1dbd3ef3afe3653705d0f34eb2df574a6d84b9b65cb274e33f`.
The continuation check made no model calls, placed no orders, injected no
synthetic production records, and did not change qualification or spending.

### Remaining acceptance evidence

1. Let an actual candidate pass current free qualification and the complete
   eight-stage review, then verify fresh finalization and immutable registration.
2. Confirm the journal's entry is supported by a post-decision reference quote
   before expiry. A watch that expires without entry is not a completed trade.
3. Confirm an observed stop, target or scheduled exit before the plan deadline,
   with net EUR P/L recomputed from recorded fills and disclosed assumed costs.
   A missing exit remains unresolved and cannot count as a scored result.
4. Verify the subsequent dashboard receipt and persisted lifecycle notification
   acknowledgements. A successful empty run does not establish these transitions.
5. Retain the decision, review chain, quote provenance, outcome and delivery
   evidence. One completed paper lifecycle proves integration, not profitability.

The deployed scheduler already continues collection and observation. Regular
stock admission additionally needs the exchange to open and at least six complete
contiguous five-minute opening bars; broad regular-session discovery remains to
be observed. Do not loosen the gates or manufacture a trade to close the milestone.
Discovery expansion, code-versus-AI comparison and a meaningful forward performance
sample are subsequent work, not completed by this checkpoint. The original
`market-radar` project and live brokerage execution remain outside this work.
