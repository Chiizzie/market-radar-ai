# Catalogue and chart audit — 9 November 2026

The 20:15 run captured valid single Trading212 catalogue matches for all 39
selected stocks at 20:16:15 UTC. The method workers repeated the same metadata
request; their 20:18:44 screen rejected all 39 on the catalogue prerequisite.
The old report omitted the underlying reference failure, so HTTP 429 or another
provider error cannot be conclusively distinguished from those records. Repeated
account-wide catalogue requests are avoidable regardless of the precise error.

## Changes

- Paper observers reuse the checksummed same-capture metadata for at most 600
  seconds, preserving its original observation timestamp across repeated reuse.
  Invalid, future, expired, wrong-identity, wrong-currency or failed source records
  cannot be reused; empty and ambiguous results retain those statuses. A fresh
  metadata fetch remains the fallback. Quotes, market clock and FX are refreshed.
- Reports expose metadata source/time, per-symbol match counts and reference
  failure codes. Replaying the actual capture recovered 39/39 single matches at
  the original screening time. This is a metadata replay, not a backfilled trade.
- Discovery now records per-symbol provider failures, empty IEX histories, stale
  tails, internal gap counts, missing intervals and contiguous recent-bar counts.
  Summary categories reconcile to checked symbols. No bars are fabricated.
- Three quarters of the rotating technical-screen slots favour fresh snapshots;
  remaining slots revisit the catalogue, including unavailable names. Core,
  catalyst, sector reservations, capacity limits and strategy gates remain intact.

## Chart evidence

Of 300 technically checked names, 81 were usable and 219 were rejected. Overlapping
reasons: gaps 159, stale candle 37, empty candles 53. Of the 219 rejected names,
139 had a fresh snapshot, 63 a stale/wrong-session snapshot, 15 no snapshot and
2 invalid snapshots. A fresh trade does not establish a complete candle series.

Alpaca's Market Data FAQ explains IEX is only one exchange and bars are omitted
when no qualifying trades establish a bar. This is consistent with sparse
histories, but does not prove every gap is a no-trade interval. Halts, obsolete
symbols, OTC coverage and provider loss remain possible. No automatic paid SIP
upgrade or substitution of delayed SIP data into live-entry checks was made.
Source: https://docs.alpaca.markets/us/docs/market-data-faq

The 600-second metadata cache is research catalogue evidence, not verified live
account permission. Trading criteria and the EUR20 planned-loss bound are unchanged.
