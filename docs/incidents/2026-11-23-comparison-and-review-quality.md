# Evening quote coverage and paid review availability, 23 November 2026

Times use Europe/Dublin. The main workflow at a87e9909aef83d0f5bc998047d63cf30311b459f pinned the collector and comparison watcher independently.

## Observed failures

From 08:00 through the 18:40 dispatch, 114 of 129 ordinary scanner workflows passed. Eight runs failed in account sync between 14:30 and 15:05. Seven later runs failed in the comparison watcher. Five of those seven reported only quote gaps. Two also emitted a generic stock validation error. The earlier account incident is documented separately.

The [17:50 comparison watcher](https://github.com/Chiizzie/market-radar-ai/actions/runs/45231944086/job/137893526386) recorded 62 stock-validation failures and only 11 quotes. Its logs could not distinguish a rejected session clock, currency conversion or malformed input. The [18:25 watcher](https://github.com/Chiizzie/market-radar-ai/actions/runs/45238180318/job/137915406371) recorded 945 valid quotes and an unresolved INTU gap. Both workers correctly retained a failed quality result. The patch records only enumerated validation reasons and retains the existing gate for each failure.

## What reached the user

At 18:41 the preceding 30 scanner snapshots had all reached the dashboard within three seconds. The [18:35 review job](https://github.com/Chiizzie/market-radar-ai/actions/runs/45239971704/job/137922466783) selected MBGL and then deferred it before making a model call. The ledger recorded €9.816368 settled and €0.042193 reserved against the €10 monthly cap, leaving €0.141439. The required review allowance is €0.15. The 18:41 manual audit recorded zero confirmed alert clocks that day.

The existing hourly collection message labeled successful collection as NO ACTION before the review job had run. It now labels a collection update, displays the limiting periods and remaining allowances from the capture's validated budget summary, and identifies unavailable or stale budget data. The collection and review still use their separate clocks. A collection notice does not establish that any candidate was approved. Spending limits, review criteria and notification cadence are preserved.

## Shared cash sizing replay

An offline USD-balance, code-only replay from 16:00 to 16:45 Dublin initialized both alternatives from paper report 626392, retaining the unresolved VLO exposure and €496.35 spendable. Both received the same 36 stock plans and 2,279 immutable quote envelopes. The fixed-size baseline matched stored reports 630784 and 634369 including balance, reserved capital, state counts and reasons. The alternative reduced the proposed quantity to fit available capital with a 0.1% sizing cushion. The fee, slippage, risk/reward, quote freshness, spread, entry trigger, expiry and exit rules were common.

Fixed sizing blocked all 36. Smaller sizing admitted seven. Six expired and KHC reached pre-entry invalidation. Neither arm recorded a new fill in this window. Every observed STUB quote exceeded the 20-basis-point spread gate. Several other watches had narrow asks below their triggers. The window provides no closed return comparison. The sizing alternative was an offline diagnostic and did not change the deployed protocol.

The source experiment was eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8. SHA-256 of the concatenated source event IDs in sequence order was f9d3cddbbebd27cb7dcd5831c171f239e298082be1547ecb01e9fc8ac600fcca. Guarded execution experiment 010dac634261525d61b6e4acf6a822bbae80f3adb0b2565b361b038b39ab1618 retained the original portfolio results.

Extending the same replay to 18:39:29 Dublin yielded 140 stock plans and 12,262 quotes. The fixed baseline matched production report 663486. Its 138 cash blocks and two expiries produced zero entries. The cash-sized arm had 131 net-reward blocks, seven expiries, one pre-entry invalidation, and a single MOS reference entry at 16:52:44. MOS was still open at the cutoff. Neither arm produced a closed trade in the replay. Both retained the earlier unresolved exposure. The ordered event ID digest is b95824919cf416736fcce7e176aced350bc412f66a0ec2353d17efc226a6848d.

## Opening opportunities

The opening-range paper experiment enrolled [TSLA at 14:46](https://github.com/Chiizzie/market-radar-ai/actions/runs/45197584116) and [HDB at 14:51](https://github.com/Chiizzie/market-radar-ai/actions/runs/45198504394). Replaying their two enrolment records and 26 quote events produced no eligible fill within either original one-minute window. The [30-minute route](https://github.com/Chiizzie/market-radar-ai/actions/runs/45201226295/job/137785552992) considered candidates by 15:06. The main guarded comparison enrolled its first equities at 16:12. An enrolment records a research candidate; delays must be measured from a confirmed notification to assess a person's ability to act.

## Opening-range display repair

The [18:40 workflow](https://github.com/Chiizzie/market-radar-ai/actions/runs/45240858940) retained the 18:41 capture in artifact 14849819502. The dashboard treated 79 stocks as waiting for the first 15 minutes several hours after the open. The stock context retained 24 five-minute bars. A longer chart already in the same capture retained the actual opening bars for 78 stocks.

After the first half-hour the display may use a checksummed same-symbol, same-feed chart with an identical most-recent candle, a valid receipt time and all three opening candles present in sequence. Replaying the original snapshot produced 37 stocks inside the opening range, 33 above and eight below. MDU lacked its first candle and remained unavailable. Only research diagnostics changed in the replay. If both charts have rolled past the open, the original opening levels cannot be reconstructed from that capture. This does not retrospectively produce trade alerts or populate absent candles.

Only the comparison watcher (11ab30e00a792efe981c85d42cbde98b650be750) and collector (5b8871a7f8d46bfb38708892a1dcf06d0d448a5d) are repinned. The separate method worker shares the watcher's previous base revision and keeps that pin. The next performance check is whether a fully qualified opening plan gives an acknowledged user enough time to act, with a valid bid/ask, intact stop and recorded exit.

## Approved November AI allowance

On 23 November the owner increased the November 2026 monthly AI allowance to €25. The effective policy applies from 20:12:39 Dublin through the end of November. The €1 daily and €100 lifetime ceilings continue to apply. The recurring monthly ceiling returns to €10 at midnight Dublin on 1 December.

The reviewer applies the same effective cap to its €0.15 preflight and each individual model-call reservation. The collector, dashboard usage figures and readiness report calculate period limits as of their own timestamps. November spending before approval and unsettled reservations still count. The persisted baseline metadata and seven immutable archive segments remain readable by earlier workers.

Replaying ledger revision 98010196bee0ee7111c541e30f2a9e2674679a91, with 1,899 entries, gave €15.141439 available for November after €9.816368 settled and €0.042193 held. Later reviews may change these amounts.
