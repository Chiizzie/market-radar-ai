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

### Verified delivery — 3 November 2026, 19:38 Dublin

State branch initialized once with an empty ledger. Manual run **41704988721**
at commit `a0fa02eaaa4263fc6b1d7f25024626c79009467e` succeeded:
29 focused tests passed, the sender returned
`historical_report_delivery_confirmed`, and a separate read of the state branch
confirmed snapshot `6b394a20dea07b460d9a4afe1e8fd69e17fc9de52f7e195d608b4bc80d1d650b`
as `confirmed`. The connection-test job was skipped. No paid AI call occurred.
Full local suite: 520 passed. GitHub full verification run 41704807561 succeeded.
Duplicate suppression, timeout retention and failed confirmation are covered by
local tests; a second live delivery was deliberately not attempted.

Next milestone: trusted fresh-review delivery with an explicit freshness policy,
followed by scheduled notifications and hosted dashboard integration. The current
manual sender accepts only the pinned historical example, not arbitrary reports.

## Fresh-review delivery

The paid manual plan-review workflow now offers `send_fresh_review` (default
false, effective only with `paid_analysis`). After successful export the sender
reconstructs the review from its capture, catalogue, plan and eight audited model
responses, rather than trusting an uploaded JSON file. Before reserving and again
immediately before sending, it requires completion no more than two minutes ago
and more than 30 seconds before evidence expiry. Expiry after reservation leaves
the permanent reservation in place. Telegram acknowledgement cannot guarantee
when a human will read the message; the original expiry is always printed.

Notification failure is recorded separately from successful review completion
and budget settlement. It must never cause a paid review to be rerun. No schedule
is enabled yet: the current small pilot spending cap and fresh-delivery trial
must be verified before recurring paid analysis is introduced.

### Fresh trial 41705886995 and prompt repair

Run 41705886995 completed six model calls, then stopped before debate with
review_prompt_too_large. No export or Telegram delivery was produced. Cost was
EUR 0.049889; lifetime settled EUR 0.542572, held zero, pilot remainder EUR
0.457428. The 32,000-byte limit is unchanged. Lossless columnar candle encoding
reduces this exact debate payload from 33,758 to 27,919 bytes while retaining every
bar value, source ID, original snapshot hash, news item and peer review. Tests
verify reversibility and original packet immutability. This is prompt formatting,
not evidence deletion or a larger token/spending cap.

### Fresh delivery verified: run 41706847328

At commit b427873ba60dd95bc23d9eaf183b89c4b07fdf8e, all eight stages completed
and Telegram returned fresh_research_delivery_confirmed. A separate state-branch
read confirmed snapshot 874571f09e452882fbd78c8c262bc42d1b792650c27d359a6fb827637963b50b.
The downloaded audit independently replayed successfully against the repository.
Verdict MORE_EVIDENCE_REQUIRED; never a trade authorization. Completed 19:51:38
Dublin, original expiry 19:55:00 on 3 November 2026. Export saved alongside this
document as nvda-reviewed-plan-2026-11-03-1951.json (historical once expired).
Review cost EUR 0.062313; this turn's two trials EUR 0.112202 total. Lifetime
settled EUR 0.604885, held zero, pilot remainder EUR 0.395115. Largest prompt
28,505 bytes. Local full suite 537 passed. Scheduled scans remain disabled;
Lovable database/authentication implementation awaits the pending plan approval.
