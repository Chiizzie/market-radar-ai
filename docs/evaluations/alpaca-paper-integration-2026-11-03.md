# Alpaca to EUR paper planner integration

The deterministic NVDA planner now accepts a single Alpaca IEX candle series or a single Yahoo series, rejects mixed/unsupported sources, records candle count and quality failures, and preserves source and latest candle time in each draft. Exact five-minute spacing is required. IEX drafts retain an explicit limited-market-coverage blocker.

The new combined workflow refreshes Trading 212 instrument/exchange metadata first, captures Alpaca data, then obtains indicative USD/EUR FX and runs the paper planner. Secrets are scoped to their respective read-only provider steps. The planner receives no broker or OpenAI credentials.

A fictional EUR 500 allocation and assumed 40 bps round-trip cost allowance are used. They do not represent a verified account balance or broker fee. Drafts retain the EUR 20 planned-loss ceiling, conditional breakout logic, expiry, session exit and all existing review blockers. No orders or paid AI calls occur.

## Verification

Local full suite: 401 passed. Initial integrated run 41671842833 received 20 completed IEX candles, fresh quote and 20 news items. Catalogue and FX retrieval succeeded. At evaluation the latest bar was just over 600 seconds old, so the draft correctly failed closed with no plan. Reproducing validation from the downloaded capture confirmed stale_candle. The workflow was reordered to fetch market evidence after the slower catalogue refresh; no freshness threshold was relaxed.

## Next review contract

The current paid research runner only supports MORE_RESEARCH_NEEDED and INSUFFICIENT_EVIDENCE; it does not review a trade plan. A subsequent paper-plan review input must bind the exact plan, catalogue identity, timestamped FX, candles and news evidence with source IDs and a digest. Independent roles must evaluate the same immutable packet, distinguish hypothetical projections from observed levels, and state unresolved blockers. Debate and final review must not clear broker, coverage, calendar, cost or expiry gates just by agreeing. Tests must cover fabricated citations, changed plans, stale evidence, arithmetic discrepancies and contradictory agent claims before a bounded paid trial.

This milestone alone does not supply an actionable trade or prove profitability.

## Verified rerun

Run 41672410407 produced a conditional_paper_draft at 16:17:23 Dublin from 21 completed candles, with no candle quality issues. Its EUR 500 fictional allocation yields quantity 2.671561 and EUR 4.18737075 planned loss including EUR 1.99203163 assumed round-trip costs. Independently recomputed risk, capital and net 2R/3R projections from the downloaded artifact passed. Six blockers remain and trade_authorized is false. The recorded draft expires at 16:22:23 Dublin and is historical test evidence, not an entry instruction.

The companion JSON retains the successful and failed runs and verified artifact hashes.

GitHub Phase 1 verification run 41672410536 and integrated Alpaca run 41672410407 completed successfully.
