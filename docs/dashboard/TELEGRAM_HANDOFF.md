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
