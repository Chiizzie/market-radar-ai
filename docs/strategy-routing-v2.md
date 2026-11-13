# Independent strategy evaluation and expanded knowledge

Hypothesis: the current single-label qualification can hide a valid continuation setup when a pullback detector takes precedence. Evaluating each compatible strategy independently on the same frozen inputs should reveal that coverage difference without loosening its gates. The additional opening-range, anchored-VWAP and competitor experiments already exist; this release connects their exact rules and source histories to a separate knowledge experiment.

Scope: six independently evaluated, long-only stock research strategies and an offline-only mean-reversion prototype. No production approval/alert/order change, paid-call activation or budget increase. The original knowledge experiment, its library and outcomes remain frozen. New inputs, protocols, plans, historical policies and overlapping same-stock alternatives are recorded separately.

Mean-reversion hypothesis: after a low-efficiency, bounded intraday range, an unusually low completed close followed by a bullish recovery may offer a conditional move toward the earlier range mean. All baseline statistics exclude the two signal bars. Parameters are predeclared in code and illustrative; offline fixtures demonstrate mechanics, not an estimated edge. No automatic promotion is based on historical fit.

Validation: preserve original qualification output by default; reproduce overlapping patterns; reject future, stale, incomplete, misidentified and missing source inputs; retain historical source/receipt clocks and outcome policies; use separate histories per strategy; cap knowledge extracts; preserve EUR20 cost-inclusive risk and intraday deadlines; exercise all seven detectors offline. Prospective preparation starts 16 November 2026. Actual outcomes and paid AI comparisons remain a later validation step.

## Implemented scope

| Strategy | Research route | Historical cases at freeze |
| --- | --- | ---: |
| 20-bar trend continuation | Independent evaluation and paired inputs | 707 |
| Trend pullback reclaim | Independent evaluation and paired inputs | 0 |
| 30-minute opening continuation | Independent evaluation and paired inputs | 5 |
| 15-minute opening-range breakout | Independent evaluation and paired inputs | 4 |
| Session-open anchored VWAP reclaim | Independent evaluation and paired inputs | 1 |
| Competitor-strength breakout | Independent evaluation and paired inputs | 0 |
| Intraday range mean reversion | Offline detector only; excluded from scheduled routes and paired AI | 0 |

`strategy_registry.py` evaluates each compatible detector against the same immutable inputs. A successful pullback detector no longer hides a separate valid continuation plan in this experiment. The original default selector and production runtime are unchanged. Multiple plans for one stock are recorded as overlapping alternatives, never additive positions or independent return observations.

The three method detectors retain their original rules and protocol identities. The expanded registry additionally checks current reference spreads and normalizes quantity downward to fit EUR500 including assumed costs. It preserves the EUR20 cost-inclusive planned-risk ceiling, net reward/risk checks and same-day exit requirements. These are simulated plan limits, not guarantees about execution or realized loss.

Mean reversion uses a 20-bar baseline that excludes both signal bars. The prototype requires a bounded, low-efficiency range, an unusually low close and a bullish recovery, and targets the earlier mean. It rejects stale or misaligned bars, non-finite data, inadequate turnover, unsuitable range behavior and insufficient target room. Its thresholds are hypotheses, not calibrated probabilities.

## Frozen evidence and provenance

The new library contains **717 setups**, not 717 completed trades. Its code outcomes are **55 closed, 631 not filled and 31 unresolved**. The five imported method setups are all not filled; they provide no new realized-performance evidence. There are no historical cases for the pullback, competitor or mean-reversion families in this frozen dataset.

- Training cutoff: `2026-11-13T21:17:12+00:00` (Europe/Dublin).
- Library built: `2026-11-13T22:19:07.593130+00:00`.
- Library ID: `b5b894a29e3cf2873e1e719ccf912a07ab525b46e1e3f93729c84d7bc134b6aa`.
- Original 712-case library retained unchanged: `48672f661769ad1007d321127bf10301b432ceb4caf3934dd509c3642d5e5f76`.
- Routing protocol: `da8455f1bce1812dde9783629ceb96ee423029e7b5029fde4fdad9a9f561c531`.
- Paired-review protocol: `1fe4a580b6a075dad2c8b3f6e07c777d894970f2c0cdb7721d7845196e32fb57`.
- Original guarded source runtime: `208f4bf5f9f1f403fb977075f0ea33912f4463b0`.
- Original method source runtime: `889f1a110f9f7ac9d88dbbbc7e9548e8fe00f2c5`.
- Read-only source export: [run 43518016893](https://github.com/Chiizzie/market-radar-ai/actions/runs/43518016893), artifact `strategy-knowledge-43518016893`, ID `14081941083`.
- Downloaded export ZIP SHA-256: `68efea7bb0c45e31feff921f33151cb04fba0b06cd78f17444c29c8080a3e51c`.

The export includes 223 accepted events from 12–13 November. The builder verifies journal IDs, sequence, partitions and server receipts; both occurrence and receipt must precede the cutoff. It replays the original method implementation without writing events or redefining old outcomes. An offline rebuild from the exported journals reproduced the complete frozen library exactly.

Core guarded outcomes and legacy method outcomes retain separate `source_protocol_id` and `source_policy` fields. Legacy method exits are explicitly labelled as lacking the later guarded-quote policy. Retrieval is restricted to the matching strategy and original source protocol, uses only earlier New York session days, and does not rank by subsequent outcome. It supplies at most three cases, one per symbol/day, within a 9,000-byte context cap. A family with no cases still receives its playbook and an explicit empty history.

## Execution and comparison boundaries

The scheduled research worker refreshes bounded histories before current quotes, reuses the validated broker catalogue, preserves source-coverage failures and saves frozen inputs, every strategy result, overlap diagnostics and prepared paired prompts as artifacts. It makes **zero model calls**, sends no alerts, writes no trade events and cannot place orders. It has no model, budget, notification or journal-write credentials.

Prospective preparation starts on **Monday 16 November 2026**, during New York regular weekday sessions and before 22:00 Europe/Dublin. Before that period or outside the session, the worker validates its installed library and writes a paused receipt before any provider access. This deployment check does not establish live-market performance. Exchange-calendar and current-reference checks also remain part of each detector's eligibility.

The paired harness uses identical current evidence, plan, model settings and trusted instructions in both arms; only the knowledge arm receives historical extracts. The prompt applies the named strategy's own news requirements. Both arms are independently validated, ordered by a reproducible hash, and rejected if inputs change, expire or lose eligibility. Errors preserve available usage evidence and leave an incomplete pair. No arm authorizes a production trade. The scheduled worker only prepares these pairs; **paid comparisons are not activated** and existing daily/monthly/lifetime AI budgets are unchanged.

## Verification and remaining evidence

The offline receipt is [strategy-routing-offline-20261113.json](evidence/strategy-routing-offline-20261113.json). It exercises all seven detectors, runs six pairs through a synthetic injected reviewer (12 synthetic invocations, zero real model calls, EUR0), and proves a valid pullback plus continuation overlap. These fixtures are explicitly marked synthetic future inputs and are not uploaded into the trade journal.

The focused suite covers source ordering, all seven detector routes, overlap preservation, exact replay, receipt cutoffs, historical-policy separation, outcome-independent retrieval, risk/capital bounds, tampering, stale inputs, deadline failures, usage retention and the worker's absence of paid credentials. The final deployment receipt records the full regression count, exact runtime pin, hosted checks and observed scheduled job.

Reproduce the offline detector and paired-input verification from the pinned research runtime (`12e7b42144b693f6ecdb86aac36b04c57c5bb694`), not the legacy main source, with:

```sh
python -m pip install -e '.[dev,market]'
python -m pytest -q
python scripts/verify_strategy_routing.py --output artifacts/strategy-knowledge/offline-receipt.json
```

Still required: future-session coverage and latency measurements, outcome observation under a declared policy for the newly retained alternatives, a separately budgeted actual with/without-knowledge comparison, and assessment on later untouched data after costs. No new profitability, win-rate or calibrated-confidence claim is supported by this release. The mean-reversion family remains offline until a separate prospective validation decision.

## Release verification

Research runtime: `12e7b42144b693f6ecdb86aac36b04c57c5bb694`. Local suite: **1,656 passed**, compilation successful. Final hosted verification: [43519887067](https://github.com/Chiizzie/market-radar-ai/actions/runs/43519887067). The scheduled workflow adds only the independent research job; all existing job definitions and pins are preserved. The deployment receipt records the subsequent observed scheduled-job result.

The new **strategy-routing job succeeded** in the normal [22:35 scan](https://github.com/Chiizzie/market-radar-ai/actions/runs/43520477027/job/132213533796). At **22:36:27 Europe/Dublin** it verified the 717-case frozen library and reported `outside_strategy_validation_or_session`, zero model calls and no trade authorization. The downloaded artifact matched its published SHA-256. This confirms deployment and the period guard; active-session qualification and decision quality remain unverified. Other long-running observers were still running when this job was checked, so this is not a claim that the whole scan had completed. See [deployment receipt](evidence/strategy-routing-deployment-20261113.json).
