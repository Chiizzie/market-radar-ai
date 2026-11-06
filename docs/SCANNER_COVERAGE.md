# Scheduled screening coverage

Updated 6 November 2026.

The scanner is bounded research coverage, not a full-exchange scan. Alpaca activity
and mover endpoints contribute up to 200 records before deduplication. The
Trading 212 catalogue filters stock candidates; it is not live account permission.

During the regular session, free candle-quality and technical screening checks up
to 100 catalogue candidates per cycle using at most four concurrent requests.
Pools above 100 rotate on a five-minute clock. Failed or stale data never qualifies.

The enrichment batch selects nine leading usable candidates plus ten rotating
candidates; Micron (MU) supplements this batch. Existing paper positions have
priority under the overall 20-stock collection bound. News, calendars, reference
checks and paper qualification run on that batch. The capture CLI explicitly
requests the 20-stock quota; qualification evaluates every rankable collected
stock, rather than only three. Unusable or insufficient-history stocks remain
reported as rejected. Deferred candidates are not represented as fully checked.

The discovery artifact records checked, rejected, not_checked, usable_count and
deferred_after_screen. The final capture records actual requested and attempted
counts. The dashboard remains a periodic research snapshot, not a streaming feed.

After a paid review, refresh targets the reviewed stock without rerunning
universe discovery or spending on another model. Quote, news, calendar, session,
FX, risk, identity and expiry validation still apply. Crypto reference collection
remains separate; this change does not clear its broker-eligibility blocker.

Paid model usage limits, maximum EUR 20 planned loss, paper-only operation,
entry cutoff and stock-history warm-up are unchanged. Wider screening is not a
promise of entries or profit.

## Paid review selection

Qualified packets are considered in rank order. Previously attempted identical
setups are skipped, so a duplicate at rank one cannot prevent another qualified
stock from being reviewed. Each stock has a sliding 15-minute cooldown recorded
as a zero-cost durable budget-ledger marker before model dispatch. Small plan or
evidence changes do not bypass the cooldown. Failures also retain the marker;
there is no automatic paid retry. Free screening continues for all candidates.
After cooldown, the stock must still qualify and have different economics or
substantive evidence; an identical setup remains suppressed for that Dublin day.
The review-selection artifact records the selected candidate and each skip reason.
Only one candidate receives paid review per scheduled run; budget limits still apply.

## Opening-session and crypto paper qualification

Stock paper screening now has a separate experimental `opening_continuation_30m_v1` profile: at least six contiguous completed five-minute IEX bars beginning exactly at the current regular-session open. It measures momentum and available-session VWAP, comparing the last three bars' volume with the earlier opening bars (minimum three). It retains the 1.5 participation threshold, positive momentum, close above VWAP, conditional five-bar breakout, fresh market clock and quotes, current symbol-linked news, EUR plan and cost-inclusive risk checks. It is not backtested and has no demonstrated profitability. At twenty bars the existing momentum profile takes over. Gaps, delayed SIP bars, premarket bars and overnight history cannot substitute for opening bars. The earliest stock review is thirty minutes after the exchange open, not a fixed Dublin clock time; incomplete data can delay it.

Crypto paper qualification uses Robinhood's official Europe public supported-asset catalogue, with a bounded HTTP fetch, exact source/scope, duplicate detection, asset name and symbol matching, checksum and 24-hour maximum age. Kraken XBT/EUR maps explicitly to Robinhood BTC; ETH, SOL and XRP also have explicit identities. This is public availability evidence, **not account trading permission**. Robinhood's documented trading API is US-only. Broker permissions and executable broker quotes remain unknown.

Fresh Kraken EUR reference quotes (maximum 30 seconds, online pair, positive sizes and uncrossed prices) provide native EUR pricing and paper observations. Crypto is eligible for free qualification on weekdays 08:00–22:00 Dublin without waiting for the US stock open. It still requires twenty completed candles, current publisher-tagged news, technical qualification, all eight review stages and fresh revalidation. The daily €1 AI cap, durable duplicate guard and 15-minute candidate cooldown apply across both markets. All entries and outcomes remain simulations with assumed costs; missing or stale catalogue/quotes block crypto before AI. The dashboard accepts the four explicitly supported crypto paper identifiers and retains signature, risk, identity and review-chain checks.

## Internal run diagnostics

Each scheduled collection/review writes `run-diagnostics.json` and a GitHub job summary, including on failure where artifacts exist. This is an internal report, not another Telegram notification or a dashboard trade signal. It separates capture/history gaps, setup conditions, session uncertainty, risk/time rules and evidence gaps; counts overlap when a candidate has multiple blockers. It retains candidates rejected before shortlisting, deferred counts and explicit collection-fallback labels when review qualification is unavailable.

Review summaries distinguish stage attempts, received assessments, a validated eight-stage chain, final decision and delivery confirmation. A partial review is not a completed call. Spending is read from the durable ledger for that packet only, with settled EUR estimates separate from unresolved reservation maxima. Missing/unreadable records are unavailable, never assumed zero. Confirmed zero-model-call paths need no ledger lookup. Reporting performs no model calls, writes no budget state and cannot change qualification, spending limits or paper admission. Diagnostic-step errors cannot hide the original workflow failure.
