# Dashboard integration review and resolution

## Resolved through direct GitHub development, 17:12 Dublin

The user clarified the preference to avoid Lovable editing-agent credits. The
integration was completed directly in `Chiizzie/pixel-perfect-replay-32614`
commit `065cc4801196e137ee1aafda0b58156684416b27`: all six producer fixtures parse,
681 offline dashboard tests pass, TypeScript passes and production build passes.
The live Performance asset `/assets/performance-B6S69pZI.js` contains the repaired
panel. No additional Lovable editing-agent calls were made. Existing database
constraints/policies were inspected; no synthetic record was inserted.

All eight findings below were addressed. The migration SQL itself was not
reapplied; the file and journal tag now use 0012 to follow the research schema.
The historical Drizzle journal alone still omits older manually applied
migrations, so complete recovery is not claimed. The new regression tests also
cover signed partition isolation, stored timestamp microseconds, report arithmetic,
viewer access, sign-out and a read completing after sign-out. Two pre-existing
TypeScript failures were reproduced/fixed at the optional RPC argument and
stored-event kind boundary. The old evidence test/error text was aligned with
the already-deployed 1000-item capacity, without changing that capacity.

The new worker has been enabled on main. See the deployment checkpoint there
for the first actual run/report; the following is the earlier review history.

## Earlier blocked checkpoint

The user approved the pending `plan--show` action on 12 November 2026. The
approval for user message `umsg_01m788snh8erebw5qtdyrczwq4`, thread `main`, event
`main:agent#00000000006410#tcb:NR4LLP4F`, was accepted at approximately 16:52
Dublin. The resumed turn completed a **partial** implementation in commit
`7b59aab79e14c59aee3574df9d060d20dba49458`. It reports an existing
`src/lib/market/opportunity-page.test.tsx` typecheck error; tests and browser
checks were not completed, and the app was not published.

A follow-up specifying the six fixes below and attaching the exact synthetic
producer fixture was refused with: "Your workspace is out of credits, so
Lovable can't send this message." No follow-up message ID was created. This
is an editing-credit blocker, not another pending user approval, and not the
scanner's OpenAI allowance. After capacity is restored, resume the focused
fix request through Lovable; do not publish the partial commit as-is.

The committed parser was read and independently exercised offline with the
unchanged producer fixture. Empty report and screen parse successfully.
Enrolment fails on unrecognized cohort safety fields; watching and closed
reports fail `Unsafe strategy paper plan`. The defects below are still present.
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
7. The panel currently says full validation begins 13 November without the
   activation condition. Change this to planned validation only after actual
   activation, so a delayed launch cannot mislabel unobserved sessions.
8. The new migration is named `0004_isolated_strategy_experiment.sql`, ahead
   of the existing `0006_research_events.sql` that creates the affected table.
   Review clean-database replay/journal ordering and use a later unique migration
   name as appropriate. Do not reapply destructive migrations or assume that a
   successful change to the existing database proves clean recovery works.

Read-only production checks confirmed the expanded kind constraint, exact
protocol/paper flags constraint and viewer policy allowing only this protocol's
strategy reports. No new-protocol records exist; raw enrolment/screen/quote
events remain excluded from viewer policy. No synthetic fixture was ingested.

Completion checks after fixes: parse all six fixture payloads (including quote),
negative safety/count/finite/partition tests, role and sign-out regression tests,
existing research-events/opportunity/Performance checks, typecheck and production
build. Check parsed timestamp equality across Postgres normalization. Then
publish and verify actual publication before enabling the prepared worker.

Complete migration and parser/RLS/sign-out tests, then verify a production report
and viewer rendering after the new backend worker is explicitly activated. A
completed Lovable turn alone is not a verified build or publication.
