# Revised Bitcoin/EUR paid trial — 2 November 2026

Run: https://github.com/Chiizzie/market-radar-ai/actions/runs/41544061985

Tested commit: 1302bdcac5a957162f1077fdf284bbae32e4eb86. Artifact ID: 13188650217. Exact input and partial report are retained in crypto-retest-2026-11-02.json.

## Result: blocked, not accepted

Five paid calls were made. Opportunity hunter, technical analyst, news analyst and devil's advocate passed automated validation. All sixteen structured metric claims matched the computed values and native EUR currency. Their summaries were complete and under the limit. Risk-manager output failed local response-quality or metric validation. The remaining specialist, debate and conclusion were not run. No trade was authorized and no automatic retry was made.

The capture high was EUR 68,876.0, low EUR 68,426.1, first close EUR 68,815.9 and last close EUR 68,540.3. These differ from the earlier trial because the capture window changed. The devil's advocate called the window high a session high; that scope is not established for a continuously trading market. Automated numeric equality does not prove semantic accuracy.

The failed field and rejected draft were not retained by the tested revision. The exact rejection cause therefore cannot be reconstructed from this artifact. Do not infer that it was a price error, truncation, or a false positive.

## Cost

- Settled before: EUR 0.148749.
- Trial: EUR 0.027361 (five calls, including the rejected response).
- Settled after: EUR 0.176110.
- Outstanding holds: zero.
- Remaining lifetime allowance: EUR 0.323890.

These are usage/pricing/FX-based ledger estimates, not an invoice reconciliation. The EUR 0.50 lifetime cap is unchanged. ENABLE_LIVE_RESEARCH was restored to disabled and verified in GitHub settings.

## Offline follow-up

Local semantic rejections now retain field paths and error types, plus a size-bounded rejected JSON draft clearly marked untrusted and trade_authorized=false. Rejected content is never promoted to an assessment or sent to peers. Provider exception text is not logged. Drafts exceeding the diagnostic storage bound are omitted with an explicit flag. This does not retrospectively recover the risk-manager response from this run or cover provider-level failures before a parsed reply is returned.

Validation after the diagnostic change: 319 local tests passed. This change adds observability; it does not relax checks or fix an unidentified rejection cause. No additional paid trial was launched.
