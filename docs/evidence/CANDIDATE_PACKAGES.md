# Candidate evidence packages

The manual scanner workflow writes `candidate-packages.json` alongside its
capture and shortlist. Packages are built for the selected stock and crypto
candidates, with the same six role specialists for every symbol. Selection is
recomputed from validated capture data; a supplied shortlist is not trusted.

Each package includes original capture provenance and candles, content-addressed
source IDs, explicit symbol-linked news, source timestamps, expiry, native quote
currency, unresolved evidence, six required roles and paper-only constraints.
The package digest detects content changes, not provider identity or authenticity.
Verification checks content integrity and expiry only; it is not a trade gate.
Source text is untrusted evidence, never instructions for an agent.

News must have been retrieved within 15 minutes and published within seven days.
Articles older than one hour are context only and cannot satisfy the current-news
requirement. Query context does not establish a ticker link. Crypto news remains
unconnected until an explicit asset/pair identity adapter exists. Invalid or
missing news produces an explicit gap while valid market evidence is retained.

Stock prices retain their native currency. EUR reporting does not convert USD
prices: missing fresh FX is explicit. Intended broker is not verified eligibility.
Quotes, costs, account permission, catalysts, exchange sessions, EUR plans and
agent review remain missing unless separately established. Every package has
`trade_authorized: false`, `plan: null`, `review_status: NOT_RUN`, and zero model
calls. Expiry is at most 60 seconds and cannot extend market/news freshness.

## Verified checks

The full local suite passed **596 tests**, including ten package cases covering
non-NVDA equities, crypto, unrelated/query-only news, stale evidence, integrity,
expiry, input isolation, USD/EUR separation and malformed feeds.

Historical integration replay used downloaded capture 41718634698 at its original
dashboard generation time, 2026-11-03 21:06:29.415349 Europe/Dublin. Five packages
passed integrity/expiry checks: TSLA, GOOGL, AAPL, ETHEUR and SOLEUR. None had
explicitly linked news in that feed. This is a historical verification, not fresh
market evidence or five trade calls. No provider connection or paid model call
was made during this replay.

## Remaining connections

The packages are workflow artifacts, not yet part of the signed dashboard schema.
The existing paid review runner still uses its NVDA-specific test path. It is not
automatically invoked by package creation. Next, generalize review input and
source-citation validation, preserve staged budget controls and abstention, then
version the dashboard contract to show package coverage and agent evidence.
Broader symbol discovery and independent stock/crypto catalyst coverage remain
separate outstanding work. No schedule, spending cap or live-order path changed.
