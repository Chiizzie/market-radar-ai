# Six-role paper research simulation

Run `python -m market_radar_ai.agents.demo` for the default objection scenario,
or add `--scenario supported` for a fictional accepted paper plan. Both print a
structured audit record and make zero network/model/order calls. The fixture date,
prices and evidence are synthetic. These commands are not market recommendations.

The six roles are opportunity hunter, technical analyst, news analyst, devil's
advocate, risk manager and final decision. All six receive separate copies of the
same immutable input, with no peer reports. The snapshot hash binds their output.
Once all six reports validate, structured debate collects objections, missing data,
opposition/abstention and missing supporting evidence. The decision role then
adjudicates the complete reports and debate. This is seven logical invocations
across six roles, not seven agents.

This increment is deterministic orchestration, not six working AI analysts. Debate
is conservative objection aggregation, not model-generated rebuttal rounds: no
objection is automatically marked resolved. All six must support with known source
IDs and no unresolved issues before a plan can pass. Source IDs prove provenance
membership only; they do not prove a claim is factually supported by a source.

The old unrestricted AnalysisPipeline stub is replaced by the guarded PaperTeam.
`pipeline.prepare_research` re-runs data admission before constructing its input.
Direct ResearchInput construction is intended for tests/trusted internal callers,
not an external API. Broker verification and FX authenticity still depend on the
upstream trusted adapters and mapping work.

## Hard constraints

- Only exact SimulatedAgent instances are accepted; paid adapters are disconnected.
- Quality, freshness, broker/asset match and broker-verification expiry are checked
  before any role invocation. Snapshot missing data blocks the run.
- An input is immutable, including its nested tuples. Reports must match role and
  snapshot hash; unknown source IDs and malformed output fail closed.
- Call budgets persist across runs when the same UsageBudget is reused. Calls are
  reserved before invocation; failed invocations consume their reservation.
- Final adjudication needs its own remaining call reservation.
- Only long paper plans are supported for Invest/spot-crypto scope.
- Prices and quantities are finite positive Decimals; stop < entry < target.
- Planned loss is recalculated from entry, stop, quantity and explicit estimated
  costs. It cannot exceed EUR 20. Actual losses can exceed planned stop risk.
- Entries at/after 22:00 Europe/Dublin are blocked. Exit deadline must be in the
  future on the same Dublin calendar date, no later than 22:00.
- Rejected plans are removed from the returned decision. Verdicts are PAPER_PLAN
  and NO_ACTION; simulation never emits ACTIONABLE_NOW.

## Not implemented yet

No paid model adapters, real prompts/inference, factual claim verification,
model-generated debate, persistent daily token/cost enforcement, chart generation,
paper fills, scheduled liquidation, outcome/accuracy tracking or deployment.
The usage ledger is process-local and single-threaded; its zero cost is accurate
only because this implementation performs no paid calls. A future paid integration
must reserve token and monetary limits before requests, record actual usage and
handle timeouts. No simulation report demonstrates profitable trading performance.

## Persistent simulation audit

Use `storage.run_and_record(team, snapshot, run_id=..., store=TeamAuditStore(path),
now=..., plan=...)` to atomically persist the full input and result (all reports,
objections, rejected/accepted verdict and logical usage). A repeated run ID with
the same snapshot returns the original historical result without spending more
calls; use a NEW ID to request re-analysis, change the plan or use a new clock.
Retries are retrieval of history, never renewed trade authorization. Conflicting
writes cannot overwrite prior evidence. Disk errors propagate; no decision is
returned as successfully recorded. This is a single-process orchestration API;
concurrent execution exactly-once semantics are not implemented. Local SQLite is
not tamper-proof storage and needs durable hosting/backups before deployment.

Preflight now validates plan risk and exit deadline before role calls, preventing
obviously invalid plans from consuming even the simulated budget. Outcomes and
agent accuracy still need a separate paper-fill and evaluation implementation.

## Prompt and spending preparation

`agents.prompts` defines six distinct, versioned evidence-grounding instructions.
They are not yet sent to models. `agents.spending.SpendingLedger` atomically reserves
integer micro-EUR against a Dublin-calendar-day cap in SQLite. Pending or unknown
usage retains the full reservation. Duplicate request IDs cannot trigger another
reservation; settlements are idempotent and conflicting changes are rejected.
Overruns are recorded before raising an error. All workers must share the same
ledger and configured cap. This does not bound a provider's billing by itself:
future adapters must calculate a conservative maximum using verified prices,
input/token limits and output caps before reserving, and settle actual usage.
No paid adapter or pricing configuration is connected in this increment.
