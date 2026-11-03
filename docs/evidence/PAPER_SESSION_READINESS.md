# Paper session readiness

Every fresh plan-review run now writes session-report.json, including dry runs,
missing-plan runs and failed runs. This is a per-candidate audit record, not a
market-wide session journal or proof of profitable performance.

It records the actual runner state, whether a validated eight-stage export exists,
plan expiry and EUR20 planned-risk checks, outstanding blockers, and NOT_OPENED
outcomes with null P&L/accuracy. A completed research review removes only the
'review not run' status; it does not clear broker, pricing or catalyst gaps.

Live validation should include a rejected/no-plan session as well as any eventual
admitted paper trade. Never manufacture a fill or score a rejected candidate as a
winner. The existing quote-replay simulator requires an accepted recorded plan
and observed bid/ask evidence. Quote replay now supports explicit limit and breakout entry modes. Breakout
mode requires an observed ask at/above its trigger, preserves pre-trigger stop
invalidation and rejects trigger-gap risk above EUR20. It remains a simplified
simulation without volume/queue/slippage modelling. Admission and observed quote
collection are still required; drafts are never automatically converted to trades.

## Broker API review — 3 November 2026

Official references inspected:
https://docs.trading212.com/api/instruments
https://docs.trading212.com/api/section/authentication
https://docs.trading212.com/api/section/general-information/api-limitations

Catalogue metadata describes instruments; the documented response does not supply
a current account-specific buy-permission or executable bid/ask field. Account
summary covers account/cash information. Do not assume either replaces a broker
permission and price check. No new account data was fetched or published here.

## Next admissions work

Define auditable account confirmation and broker quote/cost evidence with explicit
source, observation time and expiry. Integrate that evidence with decision admission
before scheduling a paper pilot. Keep cost assumptions, external research quotes,
calendar checks and independent catalyst relevance separately visible. No live
orders or new trading permissions are enabled by session accounting.

## Verified run and tests

GitHub dry run 41721924057 (commit 3c617d4a496127b05d7c710193b11d2e85543e71)
completed with no_reviewable_plan / alpaca_capture_invalid_or_stale and zero model
calls. Downloaded artifact 13272462292 verified digest
c8dc64617a851d0bc1c8ed1b8088613e0c101f910d0c53f770850554e1fdc94b.
Its session report correctly recorded UNREVIEWED_NO_TRADE, no position and null
P&L/accuracy. This verifies rejection accounting, not an admitted paper session.
The expanded local suite including breakout quote replay passed 579 tests.
