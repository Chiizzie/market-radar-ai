# Competitor catalyst discovery — 9 November 2026

User request: follow a company headline to related companies, prompted by Nvidia
news and manually identified AMD/Intel opportunities. This release adds research
routing and a separate observation report, not a new trade-entry strategy.

## Implemented

- A sourced NVIDIA ↔ AMD and NVIDIA ↔ Intel competitor map, based on NVIDIA's
  2026 annual report competition section. No unsupported AMD ↔ Intel edge or
  claim that all chipmakers have identical exposure.
- Three concurrent bounded Alpaca news requests using existing credentials.
  Each response is limited to ten tagged headlines. Discovery accepts publication
  within 24 hours and recent retrieval; stale, future, unrelated and duplicate
  items cannot create additional hypotheses. Headlines remain untrusted evidence.
- Explicit indirect attribution, headline URL, evidence ID, publication and
  retrieval times, relationship source, and unknown direction. No automatic
  classification of a headline as adverse or favourable.
- Related catalogue names reserve technical-screen slots and up to four detailed
  research slots after the liquid core. Bad technical data remains excluded.
  Existing active paper watches retain collection priority. No scan cap increase.
- Independent post-news price-response observation: aligned start/end timestamps
  within 60 seconds, fresh observations within 180 seconds, 1–30 minute windows
  starting after publication, target gain >=0.25%, target outperformance over the
  news company >=0.5 percentage points, target observed turnover >=USD10m.
  These frozen exploratory thresholds are not validated trading parameters.
- `competitor-catalysts.json` joins hypotheses to actual selection and qualification
  blockers. Scheduled job summaries list response and admission states. Missing
  assessment is distinct from approval. Reports remain workflow artifacts, not
  a new dashboard panel or Telegram alert.

## Limits and next milestone

This is a bounded semiconductor pilot, not whole-market semantic news discovery.
A headline can create a research lead without demonstrating any price response.
A positive response is consistent with rotation, not causal proof or an entry.
There are no model calls, extra paid AI calls, live orders, new simulated fills,
changes to the EUR20 limit, or weakened direct-news/volume/entry checks.

The existing 1.5x intraday volume gate can still block AMD. An independently
versioned entry/outcome arm with its own evidence and participation rules is
still required before indirect catalysts can qualify trades in their own right.
Do not count discovery rows as trades, outcomes, or proof this would have caught
an earlier move. First observation requires a post-publication price baseline.

Deployment flag: ENABLE_CATALYST_LINKS=true on the scheduled collection job.
Rollback: disable the flag or restore the prior pinned source SHA.

## Follow-on: independently tracked paper entry arm

Added `competitor_strength_breakout_shadow_v1`, protocol
`c490e29db9222f695a6a84ef5ef5f8b4a86c6e6033d1ed23d713752ac7d943dd`.
This supersedes the earlier “entry arm still required” status above.

A live 17:05 discovery capture revealed publisher-tag-only false connections
(e.g. AMD tagged on a headline about another chipmaker). Both discovery and paper
admission now require the headline to name the source company (or Jensen Huang
for NVIDIA). This is a relevance filter, not semantic sentiment analysis.

The separate paper arm recomputes competitor outperformance using fresh snapshots
and the prior collection's prices, requiring aligned post-publication windows.
It requires six contiguous completed regular-session bars, latest completed-bar
age <=360 seconds, close above six-bar HLC3 VWAP and the last-three-bar opening
price, >=USD1m last-three-bar turnover, and a positive three-bar range <=5%.
Entry is three-bar high +10bps; stop is three-bar low. Target is cost-inclusive
2R capped at a disclosed projection three range-widths above entry. It does not
use the original 1.5x volume acceleration gate or require direct positive news.
It still requires the target's fresh bounded news check, reference quotes, FX,
unique Invest catalogue candidate, <=20bps spread, EUR500 maximum independent
allocation, EUR20 maximum planned loss, 60-second entry expiry and intraday exit.

First durable enrolment per stock/day wins. No backdating, retry after a missed
entry, or reinterpretation of earlier gains. Polls use the existing quote worker,
with a separate protocol partition. Restore recomputes admission from frozen
inputs and replays observations. No paid AI, Telegram trade call, or live order.
The event endpoint allowlists only this exact protocol for the new strategy.

Scheduled artifact `method-shadow-<run>/competitor/competitor-shadow-report.json`
contains screen blockers, observation health, entries and resolved/unresolved
outcomes. The accompanying method-events.jsonl preserves the event backup.
These results are deliberately separate from the established performance totals;
there is no new dashboard UI panel in this release. Independent EUR500 paper
allocations are not a portfolio return; assumed costs and IEX coverage apply.

Validation: 1,323 Python tests passed, plus the subsequent worker-integration
check (four focused competitor tests); 15 endpoint tests and production frontend
build passed. Synthetic lifecycle exercised durable entry, exit, restart, daily
no-retry and protocol isolation. Live performance remains unproven.
