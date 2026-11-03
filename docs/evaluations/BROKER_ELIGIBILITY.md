# Broker evidence boundary

Catalogue checks and paper drafts now expose broker-eligibility-v1 diagnostics.
Exact ticker, ISIN, stock type, currency, exchange and freshness are verified
independently of account permission. Duplicate ticker records fail even if one
record has the expected identity. Supplied eligibility booleans cannot override
these checks. No balance, account ID or positions are fetched.

The remaining user evidence is confirmation that the installed API key belongs
to Trading 212 Invest and that NVDA is currently buy-enabled in that account.
The earlier NVDA screenshot is historical and does not establish a current
account-specific permission. A user confirmation is not an API verification and
must be labelled with its provenance and expiry if incorporated later.
No order should be submitted to test permission. No eligibility gate is cleared
by this change. Local validation: 473 tests passed.
