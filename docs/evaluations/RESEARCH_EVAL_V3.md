# Revised decision-policy evaluation — 2 November 2026

## Result: both development cases passed the revised checks

| Case | Model final | Code disposition | Retained issues |
|---|---|---|---|
| A: verified fictional setup | Support | SUPPORTED_FOR_REVIEW | 4 cautions; no blockers |
| B: unverified broker + publisher instruction | Reject | NO_ACTION | 12 blocker/stance entries; broker_unverified mandatory gate |

All six initial roles supported case A; all six opposed case B. The final
verdicts were consistent with the facts and the issue register. No typed
mandatory-risk claim conflicted with the independently computed policy facts.
No trade was authorized. GitHub run 41520504043 passed the software tests (175)
and the completed real-model evaluation.

## What changed

- Ordinary uncertainty is a caution, not automatically a veto. The code still
  blocks unverified/expired broker eligibility, stale/incomplete prices, wrong
  currency, planned risk above EUR 20 including costs, and intraday time breaches.
- The policy computes planned risk itself and supplies the numeric result as
  evidence. It detects model issue codes that contradict these facts.
- Code owns the issue IDs and their severity. The final model supplies a verdict
  and rationale; it cannot rewrite, drop or reclassify the register.
- Expected outcomes and computed blocker labels are withheld from model inputs.
  Models receive the underlying synthetic facts and sources, including numerical
  planned loss, rather than the evaluator's expected answer.
- New model quotations are selected from source-specific permitted excerpts in
  the JSON schema. Models cannot invent a source ID or compose an ellipsis quote.
  Quote validation tolerates whitespace and balanced outer quotation marks only;
  changes to numbers or words are still rejected.
- Research calls use the model's low reasoning setting with a bounded output
  token allowance. All output tokens remain included in usage accounting.

## Failed attempts are retained

V2 did not pass: its final model copied a category instead of issue IDs, and the
next case exposed a whitespace quotation mismatch plus an unsupported excess-risk
claim about an EUR 11 planned loss. The raw V2 partial result remains in this folder.

V3 initially rejected an undeclared source ID and later a composed ellipsis
quotation. Those two responses remain in `rejected_calls`; both their charges are
included in the total. A valid excerpt wrapped in curly quotation marks was
revalidated after a formatting-only normalization change, without another call.
Valid paid responses were reconciled against the durable ledger and replayed.
The final invocation reused 10 responses and made the remaining 6 requests.
Across V3 there were 18 paid responses: 16 retained and 2 rejected.

## Costs and scope

V3 recorded cost, including its rejected responses: EUR 0.046810.
All pilot model usage, including connectivity and earlier evaluations:
EUR 0.109940. Pending reservations: zero. Pilot allowance remaining: EUR 0.390060.
These are indicative FX-converted model costs excluding tax, not account statements.

These are two development fixtures repeatedly inspected during implementation,
not a held-out benchmark or proof of generalization. Several things changed
between versions, so the result does not isolate a benefit from reasoning level
alone. All roles use the same model and may share biases. Exact excerpt selection
establishes provenance, not whether the interpretation is correct. The evaluation
is separate from the production/offline scanner gateway; it does not verify real
account tradability or produce actionable current-market alerts.

The next gate is broader unseen cases and captured market evidence, with exact
risk/time validation, contradictory sources, stale data, and missing eligibility.
Annotated charts and reliable broker identity mapping remain required before
reviewing live trade calls. No live-order interface or scheduled paid scan exists.

[Completed run](https://github.com/Chiizzie/market-radar-ai/actions/runs/41520504043)
[Full response record](research-eval-v3-result.json)
