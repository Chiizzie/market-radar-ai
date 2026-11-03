# Capture discovery shortlist

A manual scanner capture now produces shortlist.json before export/delivery.
It verifies capture checksums and current-data quality, requires twenty completed
bars, rejects mixed quote currencies and missing baseline participation, then
uses the existing transparent momentum/relative-volume score. Stocks and crypto
have independent default quotas of three and two. Counts distinguish rejected
rows from valid candidates deferred by the quota.

This is discovery, not broker admission. Every candidate remains UNKNOWN for
broker eligibility and RESEARCH_SHORTLIST_ONLY; no model is invoked. The six
required admission checks remain explicit. The ranking score is not a probability
or measured trading edge. The shortlist is a GitHub run artifact; the existing
signed dashboard schema is unchanged and does not display the shortlist yet.

Historical replay of verified capture 41718634698 at its original generation time
ranked 8 stocks and 4 crypto, shortlisted 3 stocks/2 crypto, deferred 5/2 by quota.
This is a historical integration check, not fresh calls. The entire local suite
passed 586 tests; stale/tampered input and quota cases have regression coverage.

Candidate-specific evidence packages are now assembled from this shortlist;
see [CANDIDATE_PACKAGES.md](CANDIDATE_PACKAGES.md). The existing paid review runner remains NVDA-specific and
is not automatically invoked by shortlist membership. Broker account permission,
executable quotes/costs and independent catalyst evidence must remain unresolved
where no valid adapter evidence exists. No spending caps or schedules were changed.
