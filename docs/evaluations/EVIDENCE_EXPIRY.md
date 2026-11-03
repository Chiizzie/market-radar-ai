# Evidence lifetime correction

New paper plans expire no later than the earliest of the original five-minute
window, entry cutoff, session exit, latest candle timestamp plus 600 seconds,
FX observation plus 900 seconds, catalogue observation plus 600 seconds, and
verified calendar observation plus 300 seconds. A zero-lifetime plan is blocked.
The review's existing before/after-call expiry checks enforce the shorter window.

Validation: 464 local tests passed, including near-expiry FX, catalogue, candle
and calendar cases and the exact expiry boundary. No new paid run was performed.
Existing historical exports are not rewritten. Their original validation belongs
to the recorded code commit; replaying them against this stricter planner may
reject their old expiry. They remain historical and unapproved in the dashboard.

Broker evidence investigation: Trading 212 documents API access for both Invest
and Stocks ISA, so catalogue access alone does not establish the required account
type. Account-specific eligibility remains unresolved. No account balances,
positions or identifiers were fetched or added to public artifacts.
Reference checked 2026-11-03:
https://docs.trading212.com/api/section/general-information/only-for-invest-and-stocks-isa
