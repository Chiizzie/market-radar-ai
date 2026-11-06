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
