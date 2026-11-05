# Early screening and paper tracking

The collector produces `early-screening.json` without model calls. It uses the existing
hash-checked stock context. Current premarket observations need no 20-bar history.
The first three contiguous completed regular-session five-minute bars establish a
15-minute opening range. Prices remain explicitly native currency; missing first
bars, stale context, and corrupt captures cannot produce a range. IEX is partial
coverage. These are research observations, not a new validated entry strategy.
The existing 20-bar final-review eligibility rule remains unchanged.

Approved `PAPER_WATCH_FOR_ENTRY` verdicts seed a paper journal. The scheduled
adapter records them before delivery in `state/paper-journal.json` on the dedicated
`state/paper-journal` branch of this repository. Collectors reuse current IEX EUR
reference quotes and retain active symbols in their requested universe. Writes use
GitHub SHA comparison; failures/conflicts never initialize a blank replacement.
The journal stores immutable decisions and individual observations. Empty cycles
make no write. A 750 KB bound stops further writes and requires archival rather
than deleting history. Paid AI remains paused.

`paper-tracking.json` reports watching, open simulation, closed, not filled, or
unresolved states. Breakout entries use observed asks; exits use observed bids;
assumed round-trip costs are subtracted once. Gaps can exceed planned loss.
Five-minute observations can miss entry/stop/target crossings: no observed fill
is not proof no entry occurred. Deadline closure requires a quote at the deadline;
otherwise an open simulation remains unresolved. This is sampled evidence, not
execution-quality backtesting, and must not be used to advertise a win rate.

The scheduled journal uses `GH_PAPER_TOKEN` (the workflow's GitHub token with
contents write permission). It is not an AI key and cannot enable paid calls.
Reports remain workflow artifacts and also travel inside the signed scanner snapshot
as `research-diagnostics-v1`. The published Scanner and Paper journal screens validate
and render them through the existing viewer-only feed. Free collection status messages are separate from trade alerts: at most one success
and one failure notice per Dublin hour, with durable deduplication.
The final paper verdict notification remains separate.

Local tooling:

```
python -m market_radar_ai.agents.paper_tracking --journal journal.sqlite \
  --decision decision.json --capture enriched-capture.json --output tracking.json
```

Only ingest decisions produced by the trusted final-verdict pipeline. This journal
validates plan arithmetic/scope but is not an independent re-run of the eight reviews.
Routine collection is now Monday–Friday, 08:00–23:00 Europe/Dublin; an explicit
manual out-of-window verification remains available.

## Reliability and premarket correction

The readiness replay tests market expiry 16 minutes in the future, excluding the
independently validated paper-journal report. Previously that synthetic clock caused
`paper_tracking_report_clock_mismatch` and prevented delivery. The real snapshot
still validates the journal's original timestamp.

`ENABLE_DELAYED_PREMARKET=true` requests separate Alpaca historical SIP bars ending
16 minutes before request time. This uses the documented free historical window:
https://docs.alpaca.markets/us/docs/market-data-faq
These records never replace IEX captures, current quotes, or qualification inputs.
Early screening can use them only as explicitly delayed context when IEX context is
unavailable. The dashboard requires the delay label and original observation time.
No new subscription or paid model call is enabled. Actual provider availability
remains subject to verification on the account.
