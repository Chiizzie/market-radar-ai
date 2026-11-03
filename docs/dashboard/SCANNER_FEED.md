# Scanner feed integration

## Scope

Manual `scanner-dashboard.yml` captures eight requested US equities (NVDA, MSFT,
AAPL, AMD, META, AMZN, GOOGL, TSLA) using the existing Yahoo Finance adapter and
four EUR crypto pairs (XBTEUR, ETHEUR, SOLEUR, XRPEUR) using Kraken public OHLC.
These are research candles, not broker execution quotes. This is a bounded sample,
not full stock/crypto coverage. The separate NVDA paid-review flow uses Alpaca IEX.
No OpenAI, order, Telegram or scheduling calls occur in this capture workflow.

## Protocol

Explicit send_snapshot=true enables a single signed POST to the fixed published
/api/public/snapshots/ingest route. The existing REVIEW_INGEST_SECRET is provided
only to that step. HMAC-SHA256 signs exact UTF-8 timestamp + dot + body bytes.
X-Timestamp uses Unix seconds; X-Signature has the sha256= prefix.
An acknowledgement is accepted only with HTTP 200, ok=true and snapshot_id equal
to SHA256 of the raw body. Redirects, duplicates, transport errors and wrong IDs
fail without retries or secret-bearing error text.

The backend rebuilds the allowlisted v1.0 snapshot from checksummed capture rows;
it does not accept a caller-provided dashboard JSON. Data quality is rechecked at
export time. New export time does not make old candles current. Snapshot expiry
is 60 seconds, and original source timestamps remain visible. Current research
data still has NO_ACTION, UNKNOWN broker eligibility and zero reviewed agents.
The viewer must not infer a trade decision or EUR conversion from these fields.

## Manual verification

Run first with send_snapshot=false to preserve provider and export artifacts.
Provider failure remains a failed connectivity check even when a diagnostic
snapshot is exported or delivered. After the receiving route is tested and
published, a fresh manual send can verify protected reads and expiry end-to-end.
Do not resend a capture as if it were a new market observation.

Backend implementation initially validated with 562 local tests. Deployment and
provider outcomes must be recorded separately after they complete.

## Verified first provider capture

GitHub run 41715697953 on commit 9c934b2e8e45930cb9f4658efdef3536b27bc5dd
completed successfully with send_snapshot=false. At 20:47:23 Dublin on
3 November 2026, all 8 stocks and 4 EUR crypto pairs returned 60 completed
five-minute candles each (720 total); all passed capture and export quality gates.
The latest candle started at 20:40:00. These are completed bars, not tick prices.
Downloaded artifact 13270082147 was independently replayed at its original export
time and matched dashboard.json exactly. No AI calls or dashboard delivery occurred.
Artifact SHA256: 73a44eaafbc78a6c53ab99b2f0925d2e99de94de90806bb88b27c4343765fa04.

## Signed production delivery

Lovable frontend commit 9701162e7b43ad3ae6c55c4507d01f958825af30 was published
at the existing domain after review fixes and 196 provider-reported passing tests.
Root inspected the ingestion validator, protected read and auth cache handling.
The published Scanner feed control was verified to require a viewer login.

GitHub run 41716931607 on backend commit 305b40713c7674c97f37cd94be07e931bc769d6a
completed successfully, including the explicit signed delivery. Snapshot ID:
14124e322dd3dde06d96907fe2c8c81c13bc7fb2ade581c9ac60966e30b1bd5d.
Generated 20:55:30.044221 Dublin, expires 20:56:30 on 3 November 2026.
All 8 stocks and 4 crypto rows passed research freshness gates at export.
Artifact 13270880919 SHA256:
429d29f75630773b9916bd86716562877582da38368b56fd21ec2093af599073.
Root downloaded this artifact, verified its digest and reconstructed the exact
sent body at the logged generation time; its SHA256 matched the acknowledged ID.
No paid model calls, orders or notifications were made. Scheduling stays disabled.

Lovable acceptance message umsg_01m6hk3nmwegkb7m9g1t718af8 verified one matching
stored row received at 20:55:31.676 Dublin. Its published-site viewer test observed
the fresh countdown transition to stale at the original expiry, including stale
row labels. Reload only reread storage; sign-out removed protected data and
signed-out access exposed no capture. No seed data or code changes were used.
The feed contains no catalyst items yet (evidence not_connected), no agent reviews
and no trade decisions; these are distinct remaining integration milestones.

## News integration verified — 3 November 2026

Backend commit e1d024d31bafb364254da2f2f566ffc62897fb01 connects the bounded
scanner_feed news collector to both export and signed delivery. Local suite:
566 passed. GitHub run 41718634698 completed successfully and acknowledged snapshot
ba7131ec52eb4e4fd94aafc0c449860b963dbe2724170f9d43f82adc6a54209d.
Generated 21:06:29.636165 Dublin; expires 21:07:29. Artifact 13271362384 digest:
25c371a17c228d84cedd3e26bae0c46848939ba239bf9a8b24b7aab71194519b.
Downloaded evidence independently reconstructed the exact acknowledged body hash.

The feed contains 37 deduplicated items and explicitly reports partial coverage.
NVDA/MSFT/AAPL query feeds each supplied 10 leads; Fed supplied 2 items and NVIDIA
Newsroom 6 before cross-feed deduplication. Microsoft publisher delivery failed.
Query context never supplies inferred symbol attribution. Only NVIDIA publisher
items carry NVDA attribution in this capture. Crypto news is explicitly uncovered.

Lovable acceptance message umsg_01m6hkrt38eweaqghahmq0z5z2 verified the actual
stored row and published News & Catalysts screen: 37 linked items, original times,
PARTIAL FEED and STALE FEED indicators, and expired-snapshot warning. No deployment
was needed. No AI analysis, orders, new accounts or role changes occurred.
These research leads do not satisfy independent catalyst confirmation by themselves.
See ../evidence/LIVE_CALL_GAPS.md and ../FUTURE_ORDER_EXECUTION.md for remaining
call requirements and the user's future execution interest (not live activation).
