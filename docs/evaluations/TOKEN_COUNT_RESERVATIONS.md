# Provider-counted reservations — live verified

The optional OpenAIPilot constructor flag `count_input_tokens=True` counts the
same model, prompt, instructions, reasoning and structured-output format using
POST https://api.openai.com/v1/responses/input_tokens before reserving money.
The reservation uses uncached input pricing, adds the larger of 1,024 tokens or
10% input headroom, then adds the full output cap. Existing ledger caps and
actual-usage settlement remain authoritative. Count failures stop generation;
provider exceptions are redacted. There is no automatic retry or fallback.

Reference checked 2026-11-03:
https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens/methods/count

Validation: 439 local tests passed. GitHub verification run 41683081033 succeeded.
Manual run 41683166092 was cancelled while queued with no steps executed because
another waiting job shared the budget concurrency group. It was not rerun.
Fresh manual run 41683611465 on commit 65a96589ce5ef983a9af4bb3de9ec5b96433faa1
completed eight calls. Counted and billed input tokens matched exactly:
7978, 7978, 7978, 7978, 7974, 7976, 9534, 9804.
Cost: EUR 0.057291. Lifetime settled EUR 0.492683, held EUR 0,
remaining pilot EUR 0.507317. Spending limits were unchanged.

The manual paper review runner now enables counting and stops after settlement
if counted and billed input differ. Generic client default remains disabled.
Audit records preserve both counts for successfully returned responses.
The dashboard export passed independent replay against source artifacts.
Final verdict MORE_EVIDENCE_REQUIRED; no trade authorization.

Artifact digest:
cd9471f5be08b4475bd46429bff920fe87b18e66e4771984aa51d7c7910060c2
Original plan expiry: 2026-11-03T17:28:40.489307+00:00.
Public historical export: docs/dashboard/nvda-reviewed-plan-2026-11-03.json.
This validates this run, not universal token-count accuracy or trade profitability.

Lovable display verification: commit d9afd951ca619b21a619b1fc76f03ff8f4fa61c8
adds the optional historical NVDA review button through the strict import path.
The vendored JSON was independently compared to the committed backend export and
matched exactly. Lovable reports 142 passing tests, clean type checking and a
browser render of all eight reports, the exact cost and unapproved/not-live
labels. Browser checks were reported by Lovable, not independently repeated here.
No publication or live backend connection was performed.
