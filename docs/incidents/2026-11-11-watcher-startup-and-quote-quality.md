# Watcher bootstrap and prospective quote-quality repair

Date: 11 November 2026. All operational times below are Europe/Dublin (UTC today).

## Failure cause

The comparison watcher measured initial immutable-history restoration as part of its first live polling interval. At 19:55, restoration took 24.006 seconds and the outer loop reported a 27.049-second polling gap, despite steady quote cadence of at most 5.244 seconds. Four JMKE stale-quote observations all recovered within 15.146 seconds, but bootstrap time prevented the existing recovered-gap warning policy from applying. Similar classification errors affected the 19:15, 19:20, 19:25 and 19:30 runs.

This does not explain every failure: the 19:50 worker had 32 affected polls and a 110.030-second JMKE quote gap. That remains an actual coverage failure. Missing prices must not become assumed observations.

Evidence:
- [19:55 run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43091626743), comparison job 130769880138.
- [19:50 run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43090879835), comparison job 130767307848.
- [Historical execution export](https://github.com/Chiizzie/market-radar-ai/actions/runs/43091992470), 45,038 immutable source events at 19:58:43.

These comparison jobs have no paid model credentials and reported zero model calls. Today's review headroom is a separate normal budget deferral, not the cause of these errors. No allowance is raised by this repair.

## Repairs

1. Restore comparison history before starting the steady polling timer. Keep startup duration and first completed poll delay explicit. Warn when bootstrap exceeds 15 seconds; fail if it consumes the whole worker window. Slow but successful restoration still leaves the remaining window available for quotes; an arbitrary shorter startup cutoff must not suppress those observations. Failed restoration also retains its elapsed time. Steady polling gaps remain measured.
2. Apply the same bounded recovered-gap classification to the approved-paper watcher. Recovery requires same-symbol valid evidence, no outstanding gaps, only missing/stale quote errors, no notification uncertainty or capacity deferrals, affected polls at most 20%, quote gaps at most 30 seconds and steady polling gaps at most 15 seconds. Storage, invalid-quote, long-duration and unrecovered failures still fail. Raw counts and timestamps remain in artifacts.
3. Introduce `reference-quote-quality-v2` for packets assembled from 12 November 2026. A reference spread above 20 bps cannot trigger or invalidate entry. After entry, a wide quote crossing a stop, target or scheduled exit makes the exit unresolved; a later favorable quote cannot replace it. Narrow quotes retain actual gap losses. Unresolved execution simulations keep their capital and risk reserved.
4. Preserve every old packet and recorded historical outcome. The journal adds a bounded warning naming affected symbols and spreads. Today it identifies SLM 0.23%, LRCX 8.73% and MTCH 3.69%; a quality flag alone does not prove a quote was wrong or a broker fill impossible.
5. Bind the new optional policy to exact packet hashes and final decisions, reject unknown or mismatched policies, and retain all chief/reviewer rejection, freshness, risk and no-live-order checks. Update dashboard parsers before the prospective backend policy activates.

## Separate experiments

The comparison and execution protocol hashes remain immutable. Both comparison arms use the same next-session quote rule; old experiments are not recalculated with the new rule.

| Series | Comparison source | Execution experiment | Starts |
| --- | --- | --- | --- |
| Original conditional-chief | `abfaa5c8b4fd3e76a46dddd142bd4747765b32c0caf2c6122afe9dbff6c7e4e8` | `530424b310fd4096a2871f1b0ac814cab436a2f47879231c17cff1ed3a251d36` | 8 Nov |
| Quote-quality guarded | `eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8` | `010dac634261525d61b6e4acf6a822bbae80f3adb0b2565b361b038b39ab1618` | 12 Nov |

The execution workflow explicitly chooses the matching source. Historical method-shadow experiments and the original separate scanner remain unchanged.

## Verification completed before deployment

- 186 focused backend tests passed, including 20 new regression checks for startup timing, real outages, symmetric quote ambiguity, policy binding, immutable replay and retained unresolved exposure.
- 91 dashboard/parser/signed-ingestion tests passed, including actual Python-generated unresolved execution outputs and crossed-protocol/date rejection.
- Dashboard production build passed.
- Replayed all eight current paper-journal records: the complete trade rows match the old implementation exactly; only the explanatory warning note changes.
- Replayed 45,038 archived execution source events: the entire historical report is exactly equal to the production export.

## Remaining limits

The feed remains Alpaca IEX, not consolidated broker execution. A live SIP probe returned subscription-restricted HTTP 403 in the separate feed audit; delayed SIP was useful for retrospective checks only. This repair cannot create missing fresh quotes. It does not validate strategy profitability, revise trading thresholds to erase losing trades, alter live orders, or add paid AI calls.

## Production rollout and remaining verification, 20:26 Dublin

- Final runtime: `e6053db510f0a32f38685351198e42029e852da6`; scheduled and execution workflow pins deployed on main in `7c58b3e50d18ccf9c6e023fcf8735138f2e45713`.
- Dashboard commit: `de25d117c804e735cb48ff645d92b666c35608c2`. Published candidate-research and performance assets returned HTTP 200 and contained the new packet policy, exact execution hash and unresolved-exit reason.
- [Hosted regression verification](https://github.com/Chiizzie/market-radar-ai/actions/runs/43094238320): 184 tests passed against the first runtime plus the exact release scheduler. Its initial harness failure was a missing scheduler file in the runtime-only checkout; corrected by checking out that file from the release commit as well.
- The final startup adjustment adds two tests: 186 backend tests passed locally, alongside 91 frontend checks and the production build. An additional offline next-session lifecycle verified automatic policy selection, enrolment, fixture reviews, observed entry, symmetric ambiguous exit, immutable event export and reconstruction after restart without paid calls.
- [Production execution replay](https://github.com/Chiizzie/market-radar-ai/actions/runs/43094046326) succeeded on the first new runtime, including publication, operational readiness and trade evaluation.
- [20:15 scheduled run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43094756451): collection and account sync succeeded. Comparison job `130780605358` failed after about 87 seconds in its observation step. Its health artifact is `13889244889`. Direct authenticated job-log and artifact downloads repeatedly returned `ReadTimeout`; the exact recorded failure remains unconfirmed. Do not label this run healthy or assert a specific cause without reading that record.
- The first runtime introduced an arbitrary 60-second startup cutoff. This was removed from the final runtime because a successful slow restore should still use the remaining 330-second observation window. Restoration that consumes the whole window still fails, and actual slow polling, lasting quote gaps, storage errors and notification uncertainty remain failures. Failed restoration now also records elapsed startup time. This correction does not establish that the unavailable 20:15 health record had that cause.
- A bounded [evidence retrieval job](https://github.com/Chiizzie/market-radar-ai/actions/runs/43095588956) was queued to copy only that existing health JSON into `docs/incidents/2026-11-11-production-watcher-health.json`. It uses GitHub artifact access only, no model, market-data or Telegram requests.
- At 20:26 the 20:20 and 20:25 scanner runs, the evidence retrieval job, [final regression check](https://github.com/Chiizzie/market-radar-ai/actions/runs/43095979226) and [final execution verification](https://github.com/Chiizzie/market-radar-ai/actions/runs/43095979209) were queued. The GitHub and Lovable status pages reported operational; no provider-wide outage is asserted. The final runtime has not yet been demonstrated by a completed scheduled run.

Next verification: read the saved health record when available; inspect a completed scheduled run pinned to `e6053db`; confirm separate startup timing, unchanged strict recovery conditions, and signed dashboard delivery. On 12 November verify the new comparison/execution identities and first genuine guarded paper outcome. No extra live trades, AI-budget increases or paid model test calls were made.


## Follow-up verification, 21:07 Dublin

The unavailable 20:15 log was recovered through authenticated GitHub job-log access. It confirms the first repair's 60-second startup cutoff caused that comparison-worker failure: restoration completed in 86.453 seconds, followed by `comparison_startup_deadline_exceeded`, zero polls and zero model calls. The final runtime `e6053db` had already removed that arbitrary cutoff at 20:25. This supersedes the earlier uncertainty about that specific failure.

The [20:50 scheduled run](https://github.com/Chiizzie/market-radar-ai/actions/runs/43098356909) started its runners around 20:57 after queueing. Logs verify checkout of final runtime `e6053db510f0a32f38685351198e42029e852da6`:
- Comparison process: 60 polls, zero error polls, maximum steady outer polling gap 5.000 seconds; startup took 31.721 seconds, was explicitly warned, and did not prevent observation. Final process state `completed`, `critical_failure=false`.
- Paper process: 66 polls, zero error polls, no unconfirmed notifications, maximum polling gap 5.000 seconds; final process state `completed`, `critical_failure=false`.
- Both processes received zero tracked quotes, and the paper watcher reported zero active plans. This is runtime verification, not a newly observed trade lifecycle or proof of market-data completeness.
- Collection, account sync, review and market context jobs completed successfully. Review recorded `no_qualified_candidate_zero_cost`, with zero model calls. At this check, the overall workflow and watcher job metadata still reported in progress; process completion must not be described as a completed successful whole workflow.

Six scheduled runs from 20:20 through 20:45 recorded `startup_failure`; the 20:45 run has an empty job list. Other jobs had stalled on artifact transfers, and the final hosted regression check remained queued. These are distinct from the confirmed 20:15 application cutoff.

GitHub's [official status summary](https://www.githubstatus.com/api/v2/summary.json), updated at 20:59:33, now reports a major Actions outage, first posted at 20:48:25, as part of [incident dvy0t3mvh1lg](https://www.githubstatus.com/incidents/dvy0t3mvh1lg). The queued/startup/transfer symptoms are consistent with this service incident; the public report alone does not prove the cause of every earlier failed run. At 20:26 that status page had still reported operational.

Remaining: a fully completed scheduled workflow after service recovery, final hosted regression completion, and a genuine next-session guarded trade lifecycle. No additional scanner code, risk thresholds, budget limits or historical outcomes were changed in this follow-up.

## Requested verification completed, 21:10 Dublin

Two complete scheduled workflows now succeeded on the final deployed runtime:
- [20:50 dispatch](https://github.com/Chiizzie/market-radar-ai/actions/runs/43098356909), completed at 21:05:15.
- [20:55 dispatch](https://github.com/Chiizzie/market-radar-ai/actions/runs/43098810283), completed at 21:08:06.

All seven jobs passed in both: collection, comparison watcher, paper watcher, account sync, review, market context and method shadow. Both watcher logs explicitly confirm checkout of `e6053db510f0a32f38685351198e42029e852da6`. The later comparison worker completed 61 polls with zero error polls and a 5.000-second maximum outer gap; startup took 28.118 seconds and remained a retained warning. The later paper watcher completed 66 polls with zero error polls and no unconfirmed notifications. Both had zero active tracked quotes; the paper watcher reported zero active plans.

[Execution verification](https://github.com/Chiizzie/market-radar-ai/actions/runs/43099463437) also succeeded against the final runtime. It reconstructed 48,818 source events, verified restoration, published the execution report and readiness report, and completed offline trade evaluation with zero paid model calls.

A direct read of the dashboard database confirmed fresh scanner, private-account, comparison, execution, context, method and operations records. The scanner snapshot was generated at 21:07:07 and received at 21:07:09; the account snapshot was generated at 21:05:34 and received at 21:05:40. The execution record was received at 21:08:31. No account contents are reproduced here. Lovable reports published project commit `de25d117c804e735cb48ff645d92b666c35608c2` ready. Public candidate-research and performance routes returned HTTP 200, and the served performance JavaScript contains the exact new execution experiment hash and unresolved-exit reason.

The latest persisted readiness report (as of 21:08:32, received 21:09:22) now marks scanner jobs PASS. Its overall `attention_required` status is still accurate:
- Daily configured AI allowance has EUR 0.092205 available, below the EUR 0.15 start threshold. The EUR 100 lifetime allowance has EUR 95.440044 available. These are application ledger limits, not provider credit balances. No budget was changed and no paid test call was made.
- The stock reference quote probe is paused after the regular session.
- Sustained observation with active eligible setups remains pending. Successful empty-watch loops do not prove entry-to-exit coverage or profitability.
- The final hosted regression workflow remains queued; the previously completed local checks remain 186 backend and 91 frontend tests. No source code changed in this verification.
- GitHub still reports its Actions incident as active; successful scanner runs do not prove service-wide recovery.

Result: production runtime, complete workflow execution, historical reconstruction and dashboard ingestion are verified. A genuinely active guarded trade lifecycle from 12 November remains to be observed.
