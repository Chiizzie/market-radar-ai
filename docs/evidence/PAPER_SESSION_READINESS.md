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
and observed bid/ask evidence. Candle-based breakout drafts are not automatically
compatible with its limit-entry strategy and must not be silently replayed as such.

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
