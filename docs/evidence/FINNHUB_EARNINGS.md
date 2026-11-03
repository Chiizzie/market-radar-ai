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
