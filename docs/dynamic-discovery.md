# Dynamic stock discovery

The 7 November relative-activity ranking, persistent acceleration observations,
per-symbol selection traces and separate pullback paper strategy are documented
in [the discovery/pullback milestone](discovery-pullback-milestone.md).

Scheduled collection enables `ENABLE_STOCK_DISCOVERY=true` and
`SCREEN_DISCOVERY_DATA=true`. Discovery combines fresh Alpaca activity/mover leads
with a persisted Trading 212 catalogue of US stock candidates. It performs no
model calls and grants no trade or account buying permission.

## Catalogue and persistence

The catalogue is refreshed independently of mover availability. Exact `_US_EQ`
Trading 212 identities with type `STOCK`, currency `USD` and a valid symbol form
the normalized universe; ETFs and unsupported identities are excluded. This is
broker catalogue metadata, not confirmation that the user's account can buy a
particular instrument. Account-specific checks remain downstream.

`.scanner-cache/discovery-universe.json` records a versioned source, original
retrieval time, sorted symbols and checksum. The collector reuses it for 24 hours,
then attempts a refresh. A failed refresh can retain the original snapshot for at
most 72 hours, explicitly marked `stale_but_valid`; it never changes the source
retrieval time. Missing, future-dated, malformed, oversized, tampered or expired
caches are not accepted. The file contains no credentials or account holdings.

The deployment template restores and saves this file using the independent
`scanner-universe-v1-` Actions cache namespace. This allows reuse across fresh
runners. Actions cache is evictable, so a cache miss requires a fresh catalogue
fetch; it is not a durable trade journal or backup. Updating the template or
merging backend code alone does not activate production: the scheduled workflow
on `main` must use the verified backend revision and these cache steps.

## Bounded research selection

Two read-only Alpaca screener requests retrieve up to 100 most-active records and
50 gainers plus 50 losers. Sources older than 15 minutes, future timestamps,
malformed symbols, HTTP failures and missing credentials are rejected. These are
provider-selected leads, not a complete exchange scan. Previous-session movers
are never presented as fresh premarket leads.

The selector reserves half the batch for fresh activity leaders and rotates
catalogue candidates every five minutes. With no fresh activity leads, all
available slots rotate through the catalogue. During regular hours, up to 100
symbols receive technical checks, including up to 50 fresh leaders, with at most
four requests in flight. Usable observations are ordered by technical priority;
up to nine leading names and ten rotating names receive detailed news, calendar
and market collection. Before the open, the 19 research slots instead combine up
to nine fresh activity leaders with catalogue rotation. The
user's MU watch and active paper setups supplement selection, with active paper
positions taking priority and the total collection capped at 20 stocks.

Premarket selection prepares research. It does not mark those symbols as
technically checked or technically usable when regular-session bars are
unavailable. The existing opening strategy still needs its required completed
regular-session bars and all news, price, currency, risk and broker checks.
Catalogue rotation is broader research coverage; it is not a new premarket
momentum strategy or simultaneous deep analysis of the whole universe. If no
usable discovery source remains, the bounded fallback watchlist is explicit.

Shortlist-specific news and calendar caches cannot reuse another shortlist's
evidence. AI quotas, budgets and paper-only rules are unchanged.

## Coverage accounting

`discovery.json`, `collection-report.json`, `run-diagnostics.json` and the GitHub
run summary distinguish:

| Count | Meaning |
|---|---|
| Catalogue candidates | Normalized stock identities in the accepted metadata snapshot |
| Fresh activity leads | Deduplicated symbols from accepted activity/mover responses |
| Candidate pool | Combined discovery population after applicable catalogue filtering |
| Technical checked | Symbols actually submitted to technical checks this run |
| Technical usable / unavailable | Outcomes of those checks, not trade eligibility |
| Technical deferred | Candidate pool minus technical checks attempted |
| Research selected | Candidate-pool symbols in the final collection batch after position priority and the cap |
| Research deferred | Candidate pool minus research selected |

Technical and research counts describe separate stages; their deferrals must not
be added. Premarket can have research selections with zero technical checks.
Supplementary active positions or fallback symbols outside the candidate pool do
not inflate discovery coverage. Counts reconcile within each stage, and invalid
or missing counts remain unknown instead of appearing as zero or full coverage.

These expanded counts are available in internal run artifacts and GitHub
summaries. The existing dashboard coverage contract still describes requested
captures; this milestone does not change its user interface or claim that the
entire catalogue was charted or reviewed by AI.

Provider documentation:
https://docs.alpaca.markets/us/reference/mostactives-1 and
https://docs.alpaca.markets/us/reference/movers-1 .
