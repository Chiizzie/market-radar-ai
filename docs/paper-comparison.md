# Specialist reviews and code-versus-AI comparison

**7 November update:** the durable production integration and current deployment
contract are documented in [forward-comparison-milestone.md](forward-comparison-milestone.md).
The deployment limitations below describe the earlier foundation. Current prompt
version is `paper-specialists-v2-chart-thesis`; the current strategy protocol is
`opening30m-momentum20-pullback-v2`.

Implemented 6 November 2026. This is an engineering foundation for a prospective
paper experiment, not evidence of profitable trading or of AI adding value.

## Review instructions

The actual paid paper-review path now uses `paper-specialists-v1` rather than
changing only the role name in a generic prompt. The opportunity, technical,
news, devil's advocate, risk and final-decision roles each receive explicit
responsibilities and rejection criteria. All six receive the same immutable
packet independently. Debate receives all six reports; conclusion receives the
six reports plus debate. Sources and peer text remain untrusted data.

The version is saved in the internal `review.json`. The dashboard archive schema,
eight-call limit, durable spending controls, deterministic risk arithmetic and
fresh finalization are unchanged. `PARALLEL_PAPER_SPECIALISTS=true` enables six
concurrent independent assessments, followed by sequential debate and conclusion.
Each specialist gets an isolated model client and token counter. All share one
ledger that serializes complete reservation/settlement transactions; generation
occurs outside that lock. Cross-process CAS conflicts still fail closed, and no
paid call is automatically retried. Set the workflow variable to `false` to return
to sequential review. Manual adapters default to sequential unless opted in.

Independent results are assembled in fixed role order, regardless of completion
order. All six see empty peer lists; debate waits for all six valid assessments,
and conclusion receives those six plus debate. Failure waits for in-flight calls
and settlements before returning, preserves each stage's audit record, and stops
the dependent stages. Thus parallel mode can incur costs for all six launched
specialists even if one fails. It does not increase the eight-generation maximum
or any spending limit. Stage durations and execution mode are saved in the local
review audit. This change does not relax material-evidence comparisons or strategy
requirements; live latency improvement remains to be measured on natural reviews.

## Prospective experiment

Each paper review run writes `comparison-cohort.json` before paid selection and
generation. It contains every code-qualified packet seen by that run, a recorded
time, fixed protocol and content hash. Empty qualification writes an empty cohort.
Saving that artifact does **not** mean reference observations have started.

`ComparisonStore` is a separate SQLite journal. It can be passed as the optional
`comparison` argument to `run_pipeline`. It enrols candidates before review,
records the review-start event before model access, stores the validated decision
chain and reconciles costs from the existing budget state. Even failed reviews
retain an incomplete attempt and any known cost/held reservation. The store never
registers a rejected candidate as an approved paper trade and cannot send orders
or notifications. Repeated identical setups retain their original enrolment and
entry window; fresh capture timestamps cannot reset the baseline.

| Series | When it may start | Treatment |
| --- | --- | --- |
| Code-only baseline | Prospective enrolment, before AI review | Original qualified plan and original expiry, using observed reference quotes |
| AI-reviewed simulation | Actual fresh final approval | Approved plan and renewed expiry; no use of entry opportunities during review |
| Rejected-candidate comparison | Same baseline enrolment | Explicit hypothetical outcome, never an approved or executed trade |
| Unreviewed or failed review | No AI approval | Separate status, not silently treated as AI rejection or zero profit |

Only quotes received after prospective enrolment are admitted. Both original
venue timestamps and local receipt times are retained. Simulated fill time is
local receipt time; a late quote cannot backdate entry or an exit before cutoff.
An AI entry also needs source evidence at or after its actual approval. The
current production journal uses its existing timestamp convention; do not blend
those outcomes into this experiment without retaining the different protocol.

The two arms use the same observation stream and deterministic breakout replay,
assumed plan costs, EUR 20 planned-risk limit and final 30-second exit window.
Missing entries, open simulations and unresolved exits remain visible and are
excluded from closed-trade performance. Sampling can miss intervening events.
Real fills, order-book depth, portfolio capital constraints and intratrade equity
are not modelled. Stop gaps can produce a simulated realized loss above planned
loss; the observer must preserve the actual reference bid rather than cap it.

## Reporting and accounting

Reports include closed net EUR results, average gain/loss and average closed P/L,
realized closed-trade drawdown, missed-or-unobserved AI entries, incomplete
outcomes, known AI cost, held maximum reservations and unreconciled candidates.
Cost history is append-only; later settlements do not rewrite earlier reports.
Unknown costs are never assumed zero.

Matched policy comparisons require a closed baseline and either a closed AI
simulation or a completed NO_ACTION decision. Only that matched calculation
uses zero trading P/L for a deliberate no-action policy; model cost still applies.
An unfilled/unobserved AI entry is not silently scored as zero. Reports disclose
excluded pairs. A complete-cohort after-AI-cost delta is absent until **every**
enrolled candidate has a comparable result and reconciled cost. Matched subsets
can still be selection-biased; neither their results nor a small forward sample
establish an edge.

Protocol version and synthetic/forward dataset type are immutable per database.
Do not mix changed strategy rules, prompt versions or synthetic rehearsals into a
forward evaluation. Specify a later evaluation period before inspecting outcomes.
SQLite backup uses its consistent backup API, preserves existing backup files,
and is covered by a restore/integrity-check test. This does not migrate the live
GitHub paper journal or provision persistent hosting.

Generate a report from an existing journal:

```sh
python -m market_radar_ai.agents.paper_comparison \
  --database /persistent/experiments/paper-v1.sqlite \
  --output artifacts/comparison-report.json
```

Add `--synthetic` only for an existing synthetic journal. The CLI refuses to
create an empty database that could masquerade as a completed experiment.

## Deployment and remaining work

Specialist instructions and the prospective comparison framework were merged in
PR #3; independent reviewer concurrency is the next deployment milestone. The
comparison store itself remains unconnected to scheduled production. No additional
AI calls, paid retries or spending-limit changes are needed to run the tests or
comparison report.

Before claiming a live code-versus-AI test, connect a durable experiment store
and a bounded quote collector covering **all enrolled candidates, including
unreviewed and rejected candidates**, before any AI response arrives. Monitor
observation gaps/capacity explicitly and back up that store. The current production
watcher observes approved plans only and cannot supply a complete baseline by
itself. Historical candles or later quotes cannot reconstruct the missing stream.
The optional comparison hook is not enabled in scheduled production by this change.
Actions caches and expiring artifacts are not a shared durable experiment database.
Activation needs persistent mounted storage (or a separately validated durable
event store), explicit initialization, missing-storage refusal, and a tested
recovery procedure. Freeze the reviewer execution mode in the experiment protocol
before collecting forward evaluation data.

Validation covers the actual paid prompt construction with mocked transport,
prospective enrolment, review-delay misses, rejection counterfactuals, stop gaps,
scheduled and missing exits, quote freshness, immutable events, partial costs,
drawdown arithmetic, synthetic isolation and backup recovery. No test writes to
the production journal, dashboard or Telegram.
