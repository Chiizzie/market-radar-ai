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

1. Restore comparison history before starting the steady polling timer. Keep startup duration and first completed poll delay explicit. Warn when bootstrap exceeds 15 seconds; fail if it exceeds 60 seconds or consumes the whole worker window. Steady polling gaps remain measured.
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

- 184 focused backend tests passed, including 18 new regression checks for startup timing, real outages, symmetric quote ambiguity, policy binding, immutable replay and retained unresolved exposure.
- 91 dashboard/parser/signed-ingestion tests passed, including actual Python-generated unresolved execution outputs and crossed-protocol/date rejection.
- Dashboard production build passed.
- Replayed all eight current paper-journal records: the complete trade rows match the old implementation exactly; only the explanatory warning note changes.
- Replayed 45,038 archived execution source events: the entire historical report is exactly equal to the production export.

## Remaining limits

The feed remains Alpaca IEX, not consolidated broker execution. A live SIP probe returned subscription-restricted HTTP 403 in the separate feed audit; delayed SIP was useful for retrospective checks only. This repair cannot create missing fresh quotes. It does not validate strategy profitability, revise trading thresholds to erase losing trades, alter live orders, or add paid AI calls.

Production rollout verification is recorded in a subsequent update to this incident note.
