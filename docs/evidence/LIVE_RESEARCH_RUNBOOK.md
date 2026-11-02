# Manual research rehearsal

Workflow: **Manual live research rehearsal**. Select development branch `phase-1/market-data-layer`. The runner deliberately rejects main, other repositories, push events and scheduled events.

## First run: no AI charge

Leave `paid_analysis` false. Select `research_target`: NVDA uses stock candles and NVIDIA newsroom evidence; XBTEUR, ETHEUR or SOLEUR uses Kraken EUR candles with news explicitly not connected. The runner validates them, and saves capture.json, news.json, input.json and status.json in the workflow artifact. It does not construct an AI client, fetch cost FX, or access the spending ledger. Stale/missing evidence fails and preserves diagnostics. For stocks, run during a market session with current completed candles. Crypto research can be tested while stocks are closed; this does not change the 22:00 entry cutoff. A successful dry run establishes input readiness only.

## Opt-in paid research

Activation requires BOTH the repository variable `ENABLE_LIVE_RESEARCH=enabled` and `paid_analysis=true` on a new manual dispatch. Neither is enabled by this code change. Existing server-side secret `OPEN_API_KEY` is mapped to OPENAI_API_KEY; never paste keys into the dashboard or logs. The workflow token accesses only this repository's existing shared budget branch.

The runner rechecks data freshness before constructing the client, and orchestration rechecks before every paid call. USD/EUR FX is for AI-cost accounting only; stock candle prices retain their native currency. Existing daily/monthly/lifetime limits are unchanged. The eight-stage sequence can stop partway if evidence expires, a reservation fails, or a response is invalid. Do not interpret a failed run as zero spend. Review analysis.json and the shared ledger for settled charges and retained holds.

Workflow reruns (attempt >1) cannot execute paid mode. New dispatches can create new packets and incur further charges, still within the shared allowance. Stable packet/stage IDs reject duplicate stage billing. No automatic retry or resume is provided. Jobs share the existing budget concurrency group. Disable the repository variable after a one-shot trial.

The conclusion is limited to MORE_RESEARCH_NEEDED or INSUFFICIENT_EVIDENCE. It does not authorize a trade, paper plan or live order. Current scope is one selected instrument from four supported targets, not broad-market research. Crypto pair identity is Kraken-specific and does not verify Robinhood account eligibility. No hosted dashboard endpoint is created by this workflow.

## Verification of this change

281 local tests passed, including activation before provider access, default dry-run isolation, stale evidence before ledger/client use, explicit paid wiring through a test ledger and stubbed analysis, and artifact preservation. No real paid API call was made. Manual workflow execution remains to be verified separately from normal CI.

## Crypto research support

Crypto uses a separate crypto-research-v1 packet with news=null, news_status=not_connected and broker_eligibility=UNKNOWN. Its immutable mandatory gaps include crypto news, Robinhood account eligibility, EUR risk/plan and catalyst significance. Source IDs identify only the validated candles; no NVIDIA news is attached to crypto. Provider identity must be Kraken and native quote currency EUR. The shared capture validator and per-call freshness checks remain in force.

The research orchestration accepts this packet explicitly, without relaxing stock news requirements. Six independent assessments, debate and conclusion were tested using stubbed HTTP and the metered client/ledger implementations. Existing paper-trade input validation rejects the crypto packet. No paid call or trade is activated by adding target choices. Local suite: 290 passed.

Live local dry-run verification on 2 November 2026 at approximately 22:42 Dublin: XBTEUR, ETHEUR and SOLEUR each returned ready_dry_run with 60 validated candles, latest completed interval 22:35 UTC, zero model calls and trade_authorized=false. All four missing-data flags were preserved. This verifies live retrieval-to-packet construction, not actual AI reasoning or broker eligibility. The manual GitHub workflow dispatch has not been executed by the connector.
