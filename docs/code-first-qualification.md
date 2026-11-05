# Code-first qualification: paid review paused

At the user's request, scheduled paid reviews are disabled and the scheduled
review job no longer receives an OpenAI key. Data collection continues.
The EUR 1/day, EUR 5 lifetime and EUR 10/month limits remain ceilings, not targets.

Each collection writes `qualification.json` alongside the capture artifact.
It reuses validated capture freshness and hash checks, ranks stock and crypto
candidates using momentum/relative volume, and attempts conditional EUR paper
plans without calling a model or any additional provider. FX is reused only
from an intact stock-reference record and validated by the planner. Rejection
reasons and counts remain explicit. A conditional plan uses fictional EUR 500
capital and assumed 40 bps round-trip costs; it is not an approved setup.

A second gate in the scheduled reviewer blocks legacy research packages before
budget access, FX fetching, quota reservation, or model construction. Removing
missing-evidence labels cannot bypass it. No existing package has a validated
final-verdict contract, so none can currently qualify for paid review.

## Remaining work before paid final verdicts can resume

- Supply and validate broker/account eligibility, current broker-relevant quote
  evidence, costs, FX, session/exit timing, and independent catalyst evidence.
- Replace the research-only decision adapter (which always returns NO_ACTION)
  with an explicitly validated paper-decision contract. AI approval must not
  override deterministic risk, freshness, identity or session failures.
- Recheck evidence after model completion; short quote expiry can precede a
  six-agent review's completion.
- Deduplicate by setup and material evidence change, persist paper outcomes,
  and measure cost per qualified verdict. No paid retry for an unchanged setup.
- Connect qualification summaries to the authenticated dashboard/Telegram
  schema. For now these diagnostics are GitHub artifacts and workflow logs.

Keep paid reviews paused until that complete path is verified. Passing local
unit tests alone does not establish live admission or profitable calls.
