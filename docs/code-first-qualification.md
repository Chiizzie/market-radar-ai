# Code-first qualification

Paid scheduled reviews remain paused at the user's request; collection continues.
The EUR 1/day, EUR 5 lifetime and EUR 10/month limits are ceilings, not targets.

Each collection writes qualification.json and paper-review-packets.json. Code
validates freshness, ranks momentum/participation, measures rolling VWAP, attempts
conditional EUR paper plans and independently recomputes risk. Paper blockers
are reported separately from the stricter live-execution unknowns.

The paper-final-verdict contract now allows a current Trading 212 catalogue match
and explicitly assumed paper costs. Unknown live account order permission is not
misrepresented as verified. Kraken quotes still cannot establish Robinhood
availability. See paper-final-verdict.md for eligibility and decision policy.

The original research package remains blocked from paid dispatch: deleting gap
labels cannot promote legacy research into a trade. The new dispatcher requires
PAPER_FINAL_VERDICTS=true and explicit paid mode. The deployed workflow has its
review job disabled and no OpenAI secret, so this change does not resume costs.

The final path binds six specialist reports, debate and conclusion to one fixed
plan and source set, refreshes provider data, then rechecks unchanged economics,
freshness, risk and time limits. A conditional PAPER_WATCH_FOR_ENTRY is simulation
only; it does not open a paper or live position. Signed archive ingestion and
Telegram use explicit paper labels. Paper fill/outcome tracking remains a
separate component; no profitable performance has been established.
