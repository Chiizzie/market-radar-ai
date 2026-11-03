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
