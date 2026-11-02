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
run. Keep `OPENAI_API_KEY` in **Secrets**, never Variables or source files.
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
