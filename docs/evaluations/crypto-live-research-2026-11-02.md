# Bitcoin/EUR paid research trial — 2 November 2026

## Outcome

Execution completed; analysis quality NOT accepted. This was research only, not a trade signal or paper fill.

- Workflow: https://github.com/Chiizzie/market-radar-ai/actions/runs/41541323164
- Tested commit: 0cd2f2e0d11c1009c8bf887689705418d356d56c
- Target: Kraken XBTEUR; 60 completed five-minute candles.
- Eight real model calls: six independent specialists, structured debate, final conclusion.
- Conclusion: INSUFFICIENT_EVIDENCE.
- Trade authorization remained false. No orders were placed.
- ENABLE_LIVE_RESEARCH was returned to disabled after this single authorized run.

## Cost reconciliation

| Ledger measure | EUR |
| --- | ---: |
| Settled before | 0.109940 |
| This trial | 0.038809 |
| Settled after | 0.148749 |
| Outstanding reservations after | 0.000000 |
| Remaining lifetime pilot allowance | 0.351251 |

These are application ledger costs using recorded usage, configured pricing and captured FX, not a reconciled OpenAI invoice. The lifetime pilot cap remains EUR 0.50.

## Quality defects found by artifact review

1. Four specialist summaries reached the 600-character limit; several end mid-sentence. The opportunity summary also ends with an unexpected mixed-language fragment.
2. The technical analyst described the highest visible price as approximately EUR 68,914.9. The supplied candle-window high is EUR 68,961.8. Citation identity validation did not prevent this numerical error.
3. The opportunity report inferred adequate liquidity from OHLC data without spread or depth evidence. That inference is not established by the supplied data.
4. Some concern strings combine multiple poorly formatted points.

Successful workflow execution is not evidence of accurate analysis or profitable trades. Do not use these outputs as actionable recommendations.

## Missing evidence retained

- crypto_news_not_supplied
- robinhood_account_eligibility_unverified
- eur_risk_and_trade_plan_not_supplied
- catalyst_significance_unverified

The final report preserved these gaps and 18 specialist concerns. The run occurred after the entry cutoff; research execution did not grant an entry exception.

## Provenance

- Artifact: live-research-41541323164-1 (ID 13187241414)
- Artifact SHA256: c7fae422bc28e47cabb63cee961f184e23a158f1e2fafa7b53dd409eb875c515
- Input digest: c6590e8189e52c4d2d002fce87fe8717f317f33ec71b21e6066ecd79f550555d
- Market citation: market:ae1d5a41dd5754efeaace3efd0dcca712ccc66e8245302258b4de323b0647824
- Candle timestamps: 2026-11-02T17:55:00Z through 2026-11-02T22:50:00Z.
- Actual window low/high: EUR 68,426.1 / 68,961.8.

## Next work, offline first

Add deterministic computed market metrics and numerical grounding checks. Require concise, complete summaries and bounded, separately structured concerns. Add regression coverage based on these observed defects before considering another paid trial. Broker eligibility, crypto news, EUR risk plans and dashboard integration remain separate acceptance requirements.

This audit is documentation only; it does not change runtime behavior or claim the defects are fixed.


## Offline remediation

The next revision introduces live-research-v2 reports with Python-computed window high/low and first/last closes, each tied to the original market citation and native currency. Model numbers must use structured metric claims; every claim is checked with Decimal equality, including currency and citation. Digits are rejected in narrative text. All eight stages use the same validation.

Narrative fields now require terminal punctuation, no ellipsis, no unexpected non-English characters, and no execution-quality terminology. Summaries are bounded at 500 characters and individual concerns at 240. Execution quality is explicitly UNKNOWN_NO_SPREAD_OR_DEPTH. A rejection stops subsequent calls without an automatic paid retry, retaining settled cost and a safe rejection reason.

These conservative checks can reject otherwise useful prose. They are not a grammatical or semantic proof: spelled-out numbers, paraphrased unsupported assertions, and misleading interpretations still require human review. Reports explicitly retain analysis_quality=requires_human_review; completed means protocol completion only. No new paid trial was performed for this remediation.

Regression data in tests/fixtures/live_crypto_trial.json preserves the original market packet and specialist responses for offline reproduction. Tests exercise the actual high mismatch, observed truncated responses, all response stages, wrong currency/citation/value, bounded concerns, stopping, and cost retention.
