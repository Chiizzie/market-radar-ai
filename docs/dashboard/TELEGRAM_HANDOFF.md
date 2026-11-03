# Research notification preparation

Successful paid-review exports now include notification-preview.json, a bounded
plain-text research summary with a stable research:<snapshot_id> deduplication
key. The renderer never sends anything, includes no entry instructions or raw
model prose, and labels every verdict unapproved. Browser/imported JSON is not a
trusted delivery source: a future sender must consume the backend-validated
export. Fixture reports, incomplete stages and malformed fields are rejected.

Local validation: 492 tests passed. No Telegram request or paid AI run performed.

Remaining delivery work: separate bot credentials, destination verification,
persistent atomic delivery ledger, explicit enable flag, expiry policy and one
manual test. A stable key alone does not prevent duplicate delivery. Ambiguous
send timeouts must not be retried automatically. Keep credentials out of logs,
artifacts, source code and chat. The old market-radar bot must remain untouched.

## Durable reservation implementation (3 November 2026)

The manual connection workflow succeeded in run 41703829161. This verifies the
connection test, not automatic report delivery.

`dashboard/delivery_ledger.py` now supplies a compare-and-swap GitHub store scoped
only to `Chiizzie/market-radar-ai`, branch `state/research-notifications`, path
`state/research-notifications.json`. Records contain snapshot identities and
reservation/confirmation status only: no credentials, chat IDs or report text.
Missing/corrupt storage, conflicting writes and uncertain writes block sending.
A reserved identity cannot be retried, even following a process restart; confirmed
identities are also blocked. Confirmation is idempotent.

This is tested infrastructure, not an enabled sender. The state branch still
needs explicit initialization and the delivery workflow must reserve successfully
before its single Telegram POST. An ambiguous POST must leave the reservation
in place. It must not retry after a timeout, failed acknowledgement, or failed
confirmation write. Do not use transient Actions artifacts as the ledger.
Remaining integration: initialize durable state, validate the trusted exported
review, enforce the chosen freshness policy, wire a manually enabled report send,
and verify its acknowledgement and duplicate rejection end to end.

## Controlled historical report sender

`telegram_report.py` binds delivery to the SHA-256 of the previously verified
NVDA export. It validates and renders the report before reserving, acknowledges
the durable reservation before making exactly one POST, then confirms only an
acknowledged response for the configured chat. Failed confirmation never enables
another send. No arbitrary file, URL, message body or AI output is accepted.

The manual Telegram workflow now has a separate `send_historical_report` switch,
default false. Its dedicated job requires the development branch and first manual
attempt. Only that job receives contents-write permission for the ledger. The
connection-test switch remains separate. Historical reports may be expired and
are explicitly labelled as such; this is not a fresh-call delivery policy.
No schedule or automatic report sending has been enabled.
