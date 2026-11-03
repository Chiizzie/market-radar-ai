# Stock-tagged news integration

The manual scanner now selects the Alpaca news provider using the existing
ALPACA_API_KEY and ALPACA_API_SECRET GitHub secrets. The Yahoo collector remains
available explicitly; its unverified search results are not relabelled as
stock-specific evidence.

Each requested stock makes one read-only request to the fixed Alpaca news
endpoint: seven-day window, ten results, no full article body, no redirects,
one-megabyte response limit and no pagination or retry. Missing keys, denied
access and rate limits remain visible. No new account or model spend is needed
to test the endpoint; actual entitlement must be verified with the existing keys.

Only an explicit matching symbol in the provider's article tags establishes
reported relevance. The original publisher and creation timestamp are kept;
updated articles do not become newly published stories. Invalid times, URLs,
tags, duplicate URLs and articles outside the window are excluded. Provider
tags are not independent catalyst confirmation. The combined feed still caps
output at 50 articles and reports truncation and individual source failures.
This is bounded sample coverage, not the entire stock market or an earnings
calendar. Empty results remain partial rather than proving no news exists.

Tests exercise propagation into a context research package, eight invalid
article cases, pagination visibility, duplicates, missing credentials, denied
access, rate limits, redirect refusal and oversized/malformed responses.
Local full suite: 721 passed. Live access verification is recorded below after
the repository workflow completes. No schedule, paid AI trigger or subscription
change is introduced by this integration.

Provider reference: https://docs.alpaca.markets/us/reference/news-3

## Verified live access, 2026-11-03

Implementation fe391afa55afdcac8a6a3c03680b1602584c2b38 passed GitHub CI
41736864939 (721 tests). Live scanner run 41737027568 succeeded in 37 seconds.
The existing keys returned ten validated stock-tagged articles per requested
stock. All eight context packages contained five linked news items each,
compared with zero in the preceding context-only verification. Articles can
appear in multiple packages; this is not a claim of forty unique stories.
Publishers included benzinga and fiscal.ai. Source identity is retained and
independent catalyst confirmation is still required.

The combined feed retained 50 items, deferred 40 and removed 23 duplicate URLs.
The Microsoft public editorial feed was still unavailable, so overall news
coverage remains partial. All eight packages reproduced exactly from the saved
capture and news at their original assembly time. The selected NVDA package
passed ready_dry_run; no paid AI calls, dashboard delivery or orders occurred.

Artifact 13279990742 checksum was independently verified:
251bf652af24094bebb8c9e307736bd92d14e98c3378f1c950953361876b39ac.
This verifies the existing account's endpoint access at this time, not a future
subscription entitlement, an all-market feed or a completed trading decision.
