# Protected stock research briefing

Optional `research_briefing` extends the existing snapshot 1.0 contract. No new
endpoint, table, credential or permission is needed: the same signed snapshot
ingest stores the unchanged raw body and the same viewer-only read returns it.
Old snapshots without this field remain valid. Every existing actionability
block remains in force. These facts were collected without a model review.

Exact shape is shown in `briefing-contract-example.json`, a real historical
capture exported at its original timestamp solely for contract tests. Do not
seed it into production or refresh its dates. It is not a current signal.

## Contract

The strict validator must allow only the fields below and reject a malformed
present briefing, not silently strip it on ingestion. Browser import may fail
unavailable but must report the partial/error state. No passthrough fields.

Envelope keys: schema_version='research-briefing-v1', assembled_at (aware ISO,
equal to parent generated_at_dublin as an instant), scope='REQUESTED_STOCKS_ONLY',
stocks_attempted, stocks_with_context, stocks_without_context (nonnegative
integers; with+without=attempted=parent stock row count), rows (0..20; length=with),
model_calls=0, trade_authorized=false.

Row keys: symbol (unique, matching a parent stock row), phase (one of
PREMARKET_CONTEXT, OPENING_CONTEXT, INTRADAY_CONTEXT, AFTER_HOURS_CONTEXT,
WEEKEND_CONTEXT), context_retrieved_at, expires_at (aware ISO), daily_bars
(integer 0..10), intraday_bars (integer 0..24), latest_daily_at,
latest_intraday_at (aware ISO or null; null iff corresponding count=0),
news_evidence_ids (0..5 unique strings referencing parent evidence items whose
symbols explicitly contain this stock), calendar (below or null), missing_evidence
(array of bounded nonempty strings), review_status='NOT_RUN', trade_authorized=false.
Both bar timestamps must be <= context_retrieved_at <= assembled_at, context
retrieval age 0..900 seconds at assembly; intraday bar must be completed (at least
300 seconds before context retrieval). Rows expire strictly after assembly and
no later than assembled+300 seconds or context_retrieved+900 seconds, whichever
is earlier. Included news and calendar retrieval must also be 0..900 seconds old
at assembly and each bounds row expiry to retrieval+900 seconds. Include no
future publication news. Phase is a clock label, not exchange holiday/halt proof.

Calendar keys: provider='finnhub', status=received|empty|partial|error|not_configured,
retrieved_at (aware ISO), request_from, request_to (valid YYYY-MM-DD dates;
0..15-day span), events (0..20), reason=null|credentials_required|
authentication_failed|access_denied|rate_limited|provider_http_error|
provider_unavailable, coverage_complete=false. Received requires nonempty events;
empty/error/not_configured require zero events. Error/not_configured have a
reason; successful received/empty/partial have null reason. Null calendar means
unavailable, not a successful empty result.

Event keys: symbol (equals row), date (valid YYYY-MM-DD inside request window),
session_hint=bmo|amc|dmh|unknown, exact_time=null,
date_timezone='provider_unspecified',
verification='provider_reported_not_issuer_confirmed'. Reject duplicate date/hint
pairs for the same stock. Dates are not midnight UTC or Dublin timestamps.
Do not invent publication time, exact release time, EPS, revenue or currency.

## Display and verification

Show stock-by-stock context on Research, with separate prior daily history count,
available intraday count, latest observation and retrieval times (Europe/Dublin),
linked news with publisher/publication dates, and calendar result including
request window. Empty says 'No event returned in this window', not no risk.
Labels: 'Evidence collected; agents not run', 'Research only; no trade plan',
'Partial coverage', provider-reported earnings require issuer confirmation.
Expired parent snapshot or row expiry makes the row inspection-only; update
from the browser clock. Historical bars never become fresh quotes. Evidence
coverage does not count as agent reviews, profitability, trade approval or EUR
conversion. Preserve unknown broker eligibility and all existing trade gates.

News screen should offer exact supplied stock-symbol filtering and a way to
view unattributed/macro news. A search query or headline mention never links a
stock. Outside text remains plain text and source links use existing safe URL
validation. Demo, imports and signed feed remain isolated. Refresh only reads
storage; no provider/API-key or paid-model calls from the browser.

Test old snapshots, valid real historical fixture, future/stale/mismatched
references, malformed dates/counts, extra fields, missing calendar, empty/error
calendar, unauthorized values, expiry transitions and signed-out cache clearing.
Do not alter the other market-radar repository or populate production with tests.
