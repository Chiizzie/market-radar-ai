# Manual research rehearsal

Workflow: **Manual live research rehearsal**. Select development branch `phase-1/market-data-layer`. The runner deliberately rejects main, other repositories, push events and scheduled events.

## First run: no AI charge

Leave `paid_analysis` false. It retrieves only NVDA candles and NVIDIA newsroom evidence, validates them, and saves capture.json, news.json, input.json and status.json in the workflow artifact. It does not construct an AI client, fetch cost FX, or access the spending ledger. Stale/missing evidence fails and preserves diagnostics. Run during a market session with current completed candles. A successful dry run establishes input readiness only.

## Opt-in paid research

Activation requires BOTH the repository variable `ENABLE_LIVE_RESEARCH=enabled` and `paid_analysis=true` on a new manual dispatch. Neither is enabled by this code change. Existing server-side secret `OPEN_API_KEY` is mapped to OPENAI_API_KEY; never paste keys into the dashboard or logs. The workflow token accesses only this repository's existing shared budget branch.

The runner rechecks data freshness before constructing the client, and orchestration rechecks before every paid call. USD/EUR FX is for AI-cost accounting only; stock candle prices retain their native currency. Existing daily/monthly/lifetime limits are unchanged. The eight-stage sequence can stop partway if evidence expires, a reservation fails, or a response is invalid. Do not interpret a failed run as zero spend. Review analysis.json and the shared ledger for settled charges and retained holds.

Workflow reruns (attempt >1) cannot execute paid mode. New dispatches can create new packets and incur further charges, still within the shared allowance. Stable packet/stage IDs reject duplicate stage billing. No automatic retry or resume is provided. Jobs share the existing budget concurrency group. Disable the repository variable after a one-shot trial.

The conclusion is limited to MORE_RESEARCH_NEEDED or INSUFFICIENT_EVIDENCE. It does not authorize a trade, paper plan or live order. Current scope is one issuer, not broad-market research. No hosted dashboard endpoint is created by this workflow.

## Verification of this change

281 local tests passed, including activation before provider access, default dry-run isolation, stale evidence before ledger/client use, explicit paid wiring through a test ledger and stubbed analysis, and artifact preservation. No real paid API call was made. Manual workflow execution remains to be verified separately from normal CI.
