# Market Radar AI — pilot handover, 2 November 2026

## Completed in this milestone

- Added a dedicated `state/ai-budget` branch for the persistent JSON budget record.
- Added GitHub file-version checks to prevent simultaneous runs overwriting reservations.
- Recorded reservations before any paid call; unknown results keep the full allowance held.
- Stored usage and settlement together, with USD charges and explicit indicative EUR conversion.
- Added a zero-cost GitHub storage check after the development-branch test job.
- Added an opt-in, single-request OpenAI connectivity check with no automatic retry.
- Kept source development on `phase-1/market-data-layer`, with no change to `main`.

Local verification: 146 tests passed, compilation passed, and both offline end-to-end
scenarios completed. GitHub run 41511017333 passed the test job and the actual
persistent-storage step; the paid-connectivity step was skipped. Three additional
interruption/round-trip regression tests are included in the follow-up commit.

No paid OpenAI request was made in this milestone. The key and account funding
have been reported configured by the owner, but API connectivity is unverified.

## One user action when ready

Set the repository **Actions variable** `RUN_OPENAI_CONNECTIVITY` to `enabled`,
then rerun **all jobs** of the latest successful development-branch verification
run. Keep `OPEN_API_KEY` in **Secrets**, never Variables or source files.
After the check, remove or disable `RUN_OPENAI_CONNECTIVITY`.

This authorizes one tiny connectivity request, not a scheduled scanner. The
current pilot allowance is EUR 0.50 total/daily, within a EUR 10 monthly ceiling;
model costs are estimated in EUR using fresh indicative FX and exclude tax.
The $15 provider credit balance is separate. A fixed request identity blocks
repeat paid requests on workflow reruns, including after ambiguous failures.
Read the job summary for the outcome; `already_attempted_no_retry` does not mean
a prior attempt succeeded. Do not delete budget entries to force retries.

## Next milestones

1. Verify the one-call OpenAI connection and usage record.
2. Connect live model reports to the six-role protocol with correct provenance;
   reports currently remain explicitly simulated and the team gateway is mock-only.
3. Evaluate saved cases with missing evidence, conflicting sources, unsafe risk,
   stale data and prompt-injection attempts before permitting trade-call output.
4. Complete broker-verified identity mapping and broad stock discovery, session
   calendars, and evidence-rich candles/features/news inputs.
5. Add annotated charts, a usable trade-call report/dashboard, paper outcome
   collection and honest per-agent evaluation metrics.

The project produces research and paper-trade calls for human review. There are
no live-order APIs. Synthetic replay P&L does not demonstrate trading performance.

## Authorized connectivity attempt — 2 November 2026

Run 41513497691 passed tests and the persistent-storage check. The connectivity
step stopped before FX retrieval, reservation or any OpenAI request because
`OPENAI_API_KEY` was empty in the runner environment. The budget record is
unchanged: EUR 0 spent and no paid reservation. The temporary commit trigger has
been removed. Check the exact repository Actions secret name and scope before
retrying; do not send its value through chat or commit it.

## Connectivity verified — 2 November 2026, 19:53 Dublin

The owner confirmed the existing repository secret is named `OPEN_API_KEY`. The
workflow now maps that secret to runtime variable `OPENAI_API_KEY`.
Run 41513971123 passed tests, persistent storage verification, and the real OpenAI
connectivity check with validated structured output from
`gpt-5.4-mini-2026-03-17`. It used 42 input tokens and 13 output tokens.

Recorded cost: USD 0.00009; EUR estimate 0.000081 using 0.8931999593255061271636529311
EUR/USD from Yahoo's 19:45 UTC observation. The durable record has no pending
hold and EUR 0.499919 of the pilot allowance remaining. This is a model usage
estimate excluding tax, not an account-balance readout.

The temporary activation trigger was removed. No further setup action is needed
from the owner for connectivity. Next is integrating real research responses with
the six-role protocol and evaluating evidence handling; the scanner remains
research/paper-only, with no live-order APIs.
