# Recurring research collection

The default-branch workflow `.github/workflows/scheduled-scanner.yml` checks out
a tested backend commit explicitly. Its source template is
`deploy/scheduled-scanner.yml`; replace `TESTED_COLLECTOR_COMMIT` with the tested
SHA when releasing. Updating the development branch alone does not update the
running scheduled collector. No code in `Chiizzie/market-radar` is involved.

## Cadence and limits

- GitHub cron targets minutes 02, 07, 12, …, 57 during UTC hours 07–22 daily.
  The Python guard permits actual collection only 08:00 inclusive to 23:00
  exclusive Europe/Dublin, including DST. First target is 08:02 Dublin.
- GitHub scheduling is best-effort and may be delayed or skip runs. A five-minute
  target is not a streaming quote service or guaranteed delivery deadline.
- A single non-overlapping job collects the existing eight stocks and four EUR
  crypto pairs. Provider responses, network time and artifact retention remain bounded.
- News and Finnhub calendar responses are cached for less than 900 seconds from
  the start of their collection. Original publication/retrieval times and hashes
  are retained. A cache miss/expiry/corruption triggers collection. Failed provider
  responses are explicit, not converted to successful empty results.
- Each cycle delivers one signed snapshot to the existing protected dashboard.
  HTTP delivery is never automatically retried. Provider failures still fail the
  workflow even if partial evidence was successfully delivered.
- No model API key, budget write token, order credential or notification token is
  passed to this workflow. It cannot run the paid candidate-review path. Six-agent
  review counts remain zero. This is recurring evidence collection, not trade calls.
- Main workflow has contents-read permission. Only the four existing data/ingest
  secrets are supplied to collection. No new account or permissions are needed.

## Manual verification and stopping

Run **Scheduled research collection** from **main**. Leave the outside-hours
checkbox off for a normal rehearsal; it will skip collection when closed. For
an explicitly requested one-off capture outside operating hours, check
`verify_outside_hours`. This never overrides trade cutoffs; all rows remain
NO_ACTION. Rerun attempts are blocked. Inspect storage before issuing a new
dispatch after an ambiguous delivery failure, since successful storage may have
preceded a network timeout.

Pause via GitHub Actions → Scheduled research collection → Disable workflow.
Re-enable there to resume. Artifact `collection-report.json` records delivery
identity, original evidence collection start, cache reuse, failures and zero
model calls. Compare two runs' `delivery.json` and `news.json` to verify new market
captures and unchanged cached news timestamps.

## Freshness remains separate

Snapshot trade-evidence expiry remains exactly 60 seconds. Briefing expiry and
market-bar freshness are not lengthened to hide gaps. The UI may separately
show recent capture receipt (up to seven minutes), delayed receipt (seven to
15 minutes), or overdue receipt (over 15 minutes) within operating hours.
Outside operating hours collection is paused. None of these receipt-health
labels verifies stock-market session, quote freshness, broker eligibility or
trade approval. Saved research remains inspectable at its original timestamps.

Sources: GitHub's official workflow schedule documentation states that scheduled
workflows run on the default branch, have a minimum five-minute interval, and
can be delayed/dropped during high load:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## Tomorrow's verification

Confirm a schedule-triggered run after 08:02 Dublin, successful signed delivery,
then a subsequent different snapshot ID. Compare original evidence timestamps
and cache reports across runs. Observe the published viewer receiving the newer
capture through its 30-second storage poll. Regular-market stock evidence will
still depend on provider coverage and exchange hours. There is no profitability
or trade-quality claim from successful delivery alone.
