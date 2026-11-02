# Historical Bitcoin research replay acceptance

This is an offline protocol test, not a live model evaluation or trading backtest.

## User-facing example based on the recorded capture

**BITCOIN / EUR — RESEARCH ONLY — NO ACTION**

- Historical candle window: 2 November 2026, 17:55–22:50 Europe/Dublin.
- Source: Kraken XBTEUR, completed five-minute candles.
- Python-computed window high: EUR 68,961.80.
- Python-computed window low: EUR 68,426.10.
- News/catalysts: not supplied.
- Robinhood Europe account eligibility: unverified.
- Spread, depth and execution quality: unknown.
- Entry / stop / target / position size: not supplied; no trade authorized.
- Analysis: requires human review. This historical example is not current evidence.

The six specialists' reports, objections and final rationale belong below this summary with their source references. A successful protocol run must never be labelled an actionable trade solely because all model calls completed.

## Verified offline scenarios

The recorded crypto packet was replayed with synthetic model responses through the real orchestration, validation and metering code. HTTP calls were intercepted and the budget store was in memory. No OpenAI request or shared-budget mutation was performed by these tests.

- One successful eight-stage sequence: six independent specialists, debate, conclusion.
- Eight separate corruptions: incorrect window high introduced at each stage. Each run stopped at that stage, preserved settled simulated usage, and produced no final conclusion.
- Historical-data expiry: replay under a later clock stopped before any request.
- Successful test conclusion: INSUFFICIENT_EVIDENCE, with all mandatory crypto gaps retained and trade_authorized=false.

The entire local suite passed: 317 tests. Reproduce with `python -m pytest -q`. Focused replay: `python -m pytest tests/test_crypto_research_replay.py -q`.

## Remaining acceptance work

A fresh, bounded paid trial is still needed to measure whether the revised instructions reliably produce accepted responses. These tests do not establish model accuracy, strategy profitability, broker eligibility, news coverage or production readiness. Paid research activation was not changed for this replay.
