# Finnhub earnings-calendar integration

The scanner uses FINNHUB_API_KEY from GitHub Actions secrets for one read-only
calendar request per stock (maximum 20 requested stocks, currently eight).
Each request covers yesterday through fourteen days ahead using the New York
date for query bounds. No retry, redirect or subscription upgrade is performed.
Responses are bounded to one megabyte and twenty events per requested stock.
Only matching symbols and dates inside the request window are accepted.

Events retain the provider's date and bmo/amc/dmh/unknown session hint. Exact
release time and date timezone are not supplied by this adapter; no Dublin
timestamp is invented. Retrieval times are aware UTC timestamps. Publication
time is not invented from collection time. Estimates and actual EPS/revenue
are deliberately omitted because the endpoint does not supply their currency.
Dates remain provider-reported and require issuer confirmation.

The enriched capture contains checksummed earnings_calendars records with
separate received, empty, partial, error and not_configured states. Empty
responses do not prove no earnings event exists. Authentication/access/rate
errors are retained without response bodies, credentials or request URLs.
The workflow saves evidence before marking a connectivity failure as failed.

Both context and momentum stock packages cite the calendar source, bound
freshness to fifteen minutes and retain all risk/eligibility/complete-calendar
gaps. Existing captures with no calendar field reproduce unchanged. Crypto
packages do not receive equity earnings calendars. This does not enable paid
reviews, scheduling, order placement or a new Lovable calendar view.

Provider references:
- https://finnhub.io/docs/api/earnings-calendar
- https://github.com/Finnhub-Stock-API/finnhub-python/blob/master/finnhub/client.py
- https://github.com/Finnhub-Stock-API/finnhub-go/blob/master/docs/EarningRelease.md

Validation: 23 focused tests pass, including six-role/debate/conclusion context
review, momentum-package reproduction, time/identity validation, failures,
oversized responses, missing credentials and stale/tampered captures.

## Verified 2026-11-03

Implementation 07532520fe2e2bd06694a83cc106c5f7f46b2a5e passed all 744 tests
locally and in GitHub CI 41738128074. Live manual capture 41738266429 succeeded
in 53 seconds. All eight Finnhub requests succeeded: NVDA, AAPL and AMD each
returned one provider-reported event in the bounded window; MSFT, META, AMZN,
GOOGL and TSLA returned empty arrays. This is not independent confirmation of
dates or assurance that no other event exists. No subscription upgrade was
needed for this check.

All eight context packages included a calendar status/source and reproduced
exactly from saved inputs at the original assembly time. The selected NVDA
package passed ready_dry_run. Its real captured evidence also passed an offline
six-role/debate/conclusion replay using a test client, with no live AI calls.
This establishes compatibility, not an AI opinion or a trade recommendation.
No dashboard delivery, Telegram notification or order occurred.

Artifact 13280311815 SHA-256 was independently verified:
f81dc821e484b4bbae6d1c504337a260a02171495dbab23aaca5f7884d6507db.
The prior real context package from run 41737027568 still reproduces unchanged.
