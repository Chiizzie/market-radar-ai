# Fresh plan-review workflow

Workflow: `.github/workflows/plan-review.yml` on `phase-1/market-data-layer`.

Push-triggered runs are always dry runs and receive no OpenAI key or budget token. A manual workflow dispatch with paid_analysis=true enables one bounded eight-call review under the existing shared ledger limits. Paid rerun attempts are rejected before provider collection. No scheduled execution or order endpoints exist.

The runner refreshes Trading 212 metadata before Alpaca candles/news/quote and indicative USD/EUR FX. It persists the original captures, deterministic draft and reproducible review packet. If the draft cannot be built it records no_reviewable_plan without calling models. Paid failures preserve status and available budget summaries; unknown attempted costs are not reported as zero. Existing output directories are never overwritten.

Registration: the same workflow file is present on main so GitHub can expose manual dispatch. Its job guard still restricts execution to the development branch; this does not merge the backend implementation into main.

Validation: 411 local tests passed. GitHub verification and dry-run preparation passed; dry-run 41674992640 produced ready_dry_run with zero model calls. Downloaded artifact SHA-256: c1987fef8911c30dff95a73ab695b6e7e4253a41417127b16c0c00c0b196f4c6.

A manual paid trial was dispatched as run 41675532620. See the companion audit for its outcome. A completed review does not authorize trading or remove outstanding account eligibility, coverage, costs, calendar or catalyst blockers.

## Paid trials and correction

First paid run 41675532620 stopped after one returned response failed validation. Its exact rejected field was not retained, a diagnostic defect subsequently corrected. Cost EUR 0.007249. Second paid run 41676230240 validated all six independent specialist responses and debate, all verdicts MORE_EVIDENCE_REQUIRED. The conclusion request failed the existing client input limit before provider submission: reconstructed canonical prompt 33,259 bytes versus a 32,000-byte limit. Seven paid responses cost EUR 0.052952. Total this session EUR 0.060201; ledger lifetime settled EUR 0.376202, remaining lifetime allowance EUR 0.623798, zero holds. No final conclusion or authorized trade exists.

Correction removes repeated validated snapshot identity, authorization flags and blocker acknowledgements from peer input while preserving every peer stage, verdict, rationale, citation and concern. Replaying the captured context produces 30,578 bytes. New outputs also cap rationale at 600 characters and each concern at 180, and the orchestrator checks actual prompt bytes before invoking the paid adapter. The fixed path has passed local tests but has not had another paid trial. Limits were not raised. Raw responses remain explicitly untrusted audit data; only a successful validated result is an accepted full review.
