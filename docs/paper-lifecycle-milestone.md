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
