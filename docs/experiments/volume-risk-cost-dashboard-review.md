# Dashboard integration review before publication

The Lovable turn requested for this feature is paused at `plan--show`, with
`{"path":".lovable/plan.md"}`. User message
`umsg_01m788snh8erebw5qtdyrczwq4`, thread `main`, approval event
`main:agent#00000000006410#tcb:NR4LLP4F`. No approval was supplied on the user's
behalf. Do not supersede this pause with another message. Read its current state
before resuming after the user's decision.

The uncommitted proposed parser was reviewed from the returned tool activity.
Before publishing, test it against the real producer's **synthetic-only** fixture
at `tests/fixtures/strategy-experiment-producer.json`. Never ingest that fixture
into production. It includes empty, watching and closed reports, source enrolment,
screen and quote payloads and explicitly marks itself `do_not_publish`.

Concrete compatibility issues in the proposed patch:

1. Reserved capital **includes the maximum entry gap, slippage and fees** and
   normally exceeds `entry_eur * quantity`. Do not enforce equality with bare
   trigger notional. Require at least that notional, the EUR500 admitted cap,
   positive finite values and exact producer economics in offline fixtures.
2. The cohort has `shadow_only:true`, `trade_authorized:false`, `model_calls:0`.
   Its strict object schema must include those explicit safety fields.
3. Actual health fields include `startup_seconds`, `last_active_symbols`,
   `last_errors` (bounded safe codes) and `last_success_at`. The initial proposed
   health allowlist uses different optional names. Accept only the actual bounded
   fields, preserving strict validation of unknown fields.
4. Database TIMESTAMPTZ serialization can normalize UTC and fractional trailing
   zeros. Compare parsed instants for stored report/envelope time binding, not
   string equality; preserve the original payload. Event hashing remains exact.
5. The existing quote kind in this protocol also carries the protocol, paper-only
   flags, `native_quote_usd` and `eur_per_usd`. Validate currency identities and
   bounded decimal fields; do not interpret them as executable broker quotes.
6. Keep the changes focused. Unrelated page metadata and unrelated test casts in
   the proposed patch should be omitted unless an independently reproduced build
   failure makes them necessary and their reason is recorded.

Complete migration and parser/RLS/sign-out tests, then verify a production report
and viewer rendering after the new backend worker is explicitly activated. A
paused or accepted Lovable turn is not a completed build or publication.
