# Conditional EUR paper planner v1

This is a deterministic research draft, not an AI-approved plan or a trading signal. It is currently restricted to NVIDIA's ordinary NASDAQ share: NVDA_US_EQ / US67066G1040 / USD / STOCK. It rejects stale or ambiguous catalogue matches, requires twenty clean completed current-session five-minute bars and recent USD/EUR FX. Catalogue evidence does not prove account-specific permission.

The conditional strategy uses the previous five completed bars' high plus one US cent as the entry threshold, and the latest three bars' low rounded down as the stop. If the latest close already meets the entry threshold, no draft is emitted. Two/three-R targets are projections under fixed cost and FX assumptions, not observed resistance or a prediction. Price confirmation, tick/quantity rules and actual fills remain unverified.

Quantity is rounded down to six decimals and limited by both a fictional EUR 500 allocation and EUR 20 planned loss including an assumed 40-basis-point round-trip cost allowance. Neither input is a verified account balance or broker fee quote. Fixed estimated costs and FX cannot guarantee maximum realised loss: gaps, slippage and FX changes can exceed the planned loss.

Drafts expire after five minutes or by the assumed session exit, whichever comes first. The proposed exit is the earlier of 16:00 New York and 22:00 Dublin; an exchange calendar remains a mandatory unresolved gate for early closes and holidays. Entries are blocked at/after 22:00 Dublin. Every result has trade_authorized=false, including a valid draft.

Explicit unresolved gates: account-specific eligibility, live bid/ask and actual costs, exchange calendar, independent catalyst review, and six-agent review of this exact plan. Existing research-only agent conclusions are not promoted to plan approval. No order endpoint or paid AI call is used by this rehearsal.

The workflow fetches fresh catalogue metadata, Yahoo candles and indicative FX. It records either a conditional draft or a blocked result. A successful workflow means the rehearsal completed, not that a plan exists. The artifact's state/failures determine that.

Validation: 376 local tests passed. New tests cover cost-inclusive loss and capital bounds, net target arithmetic, wrong instrument identity, stale catalogue/FX, insufficient candles, future candles and the entry cutoff.

First live rehearsal: workflow 41667406621 completed and recorded a blocked result at 15:49:02 Dublin on 3 November 2026: market_evidence_invalid_or_insufficient. No plan was emitted and no paid model call occurred. The combined market gate does not record which subcheck failed, so the artifact alone cannot distinguish insufficient history from other candle-quality failures. Do not report this as a successful live paper-plan generation.
