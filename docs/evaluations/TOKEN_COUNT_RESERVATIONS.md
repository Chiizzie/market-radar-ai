# Provider-counted reservations (staged)

The optional OpenAIPilot constructor flag `count_input_tokens=True` counts the
same model, prompt, instructions, reasoning and structured-output format using
POST https://api.openai.com/v1/responses/input_tokens before reserving money.
The reservation uses uncached input pricing, adds the larger of 1,024 tokens or
10% input headroom, then adds the full output cap. Existing ledger caps and
actual-usage settlement remain authoritative. Count failures stop generation;
provider exceptions are redacted. There is no automatic retry or fallback.

Reference checked 2026-11-03:
https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens/methods/count

Validation: 438 local tests passed, including mocked count payload parity,
malformed counts, timeouts, unchanged budget enforcement and settlement.
No live token-count request or paid generation was performed for this change.
The option remains disabled by default and is not yet enabled in the workflow.
Live verification must compare counted input with billed input before rollout;
this is staged support, not a claim that the runtime budget bottleneck is solved.
