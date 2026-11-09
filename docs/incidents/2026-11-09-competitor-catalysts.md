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
