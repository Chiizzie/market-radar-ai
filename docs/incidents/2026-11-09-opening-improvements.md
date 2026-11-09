# Opening coverage and freshness improvements — 9 November 2026

The post-open investigation found the method worker fetched history before slow
catalogue/FX calls. An offline 61-second delay reproduced its source-context
blocker. Affected production preparation took ~106 seconds, but old logs lack
individual request timings, so that run's exact latency source is not proven.
History now runs after catalogue/FX and before clock/quotes. Screening reports
include history, context, quote, reference-capture and bounded-news ages. Freshness
limits, risk, existing strategy rules and existing event protocol are preserved.
Readiness now samples a receipt clock after fetching the SPY quote. Regression
checks cover valid quotes newer than run start, truly future and stale quotes.

## Coverage

The 300-stock technical budget reserves catalogue-listed liquid core names and
fresh positive movers from eight curated sector groups. Detailed selection keeps
12 core slots, up to eight additional sector movers, ten technical leaders and
remaining rotation slots inside the existing 39 discovery + watched-stock budget.
Missing/unusable core observations are not represented as covered. Premarket
selection also prepares core research. These are curated routing groups, not
verified index constituents or current account trading permissions. Eligibility,
news, quote and risk checks still apply downstream. No AI budget increase.

## Separate earlier-opening paper experiment

`opening_range_15m_shadow_v1` uses its own protocol ID and durable enrolment/quote
partition. It can admit only 09:45–10:00 America/New_York (normally 14:45–15:00
Dublin; DST differences follow the exchange timezone). It requires complete
contiguous completed five-minute bars from the 09:30 open. The first three bars
freeze the range; the entry is range high +10bps, the stop is range low. No retry
after a completed post-range bar already crossed the trigger. Current ask must
remain below entry and bid above stop. Range width must be positive and <=5%;
observed opening turnover >=USD1m; latest close above HLC3 VWAP and first open.

Uses fresh bounded news query (not semantic assessment), received daily context,
unique Invest catalogue candidate, current IEX quote/FX and confirmed session.
Target is cost-inclusive 2R, capped at a **projected** three-range extension, not
observed resistance. Independent EUR500 maximum allocation, EUR20 maximum planned
loss, assumed 40bps round-trip costs, 20bps entry spread/gap limits, 60-second entry
window, exit five minutes before market close or 22:00 Dublin, whichever earlier.
Actual gap/slippage loss can exceed the planned amount. No overnight simulation.
No paid AI, orders or Telegram alerts. First durable symbol/day enrolment wins.
Existing AVWAP and AI-comparison results are not combined with this experiment.

The method worker shares data collection with this experiment and observes both
partitions. No extra runner job is added. Extra storage/observation work can add
latency, measured in each worker's health. Synthetic lifecycle tests are offline;
no synthetic candidates are written to production. Since deployment is after the
opening window, the next eligible session is the first live admission opportunity.

Reports: `method-shadow-<run>/early-opening/early-opening-report.json`, plus an
export of its durable events in the workflow artifact. These results intentionally
do not overwrite the established AVWAP dashboard. Dashboard integration is not
part of this patch.

## Missed-move explanations

`missed-moves.json` and workflow summaries join discovery selection, qualification
and actual final decisions. They distinguish not examined, too early, trigger
passed, qualification failure, not selected for paid review, AI veto and failed
post-review validation. Core names plus observed positive movers are included;
100 displayed rows maximum, with total/omitted counts. These records do not prove
missed executable profits; daily change can include overnight gaps. Source missing
or stale is explicit. Existing artifacts retain each run's report.

APLD on 9 November: all eight assessments approved; refreshed relative volume
failed. The ~43-second AI review and ~9-second refresh did not establish a lost
winning trade. The original code allows expiry renewal after fresh validation.
APLE was unreviewed under the one-paid-candidate-per-run policy, unchanged here.

## Validation

The full suite passed 1,313 tests before final diagnostic/pre-open additions.
Final focused checks and live deployment evidence are recorded in the deployment
commit. Synthetic early lifecycle covers enrolment, fill, exit, replay and isolated
storage; timing checks reject stale/future observations. Original scanner untouched.
