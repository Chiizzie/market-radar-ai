# Paper-only final verdict contract

The collector now produces `paper-review-packets.json` without any model calls.
The original research archive stays research-only; it is never relabelled as an
approved setup. A separate `paper-review-packet-v1` supplies a fixed plan and
source evidence to six independent specialist reviews, debate and conclusion.

## Paper qualification

Stocks require a current Trading 212 catalogue candidate, current IEX reference
quote converted into EUR, fresh FX and open US market clock. Catalogue evidence
means availability for simulation, not verified live account order permission.
The plan must pass independent cost-inclusive risk arithmetic (EUR 20 maximum),
capital and expiry checks, with a market-close exit. The latest reference ask
must remain above the stop and below the pending entry trigger. Positive 20-bar
momentum, close above rolling VWAP, relative volume >=1.5 and at least one current
symbol-linked news item are conservative screening heuristics, not a validated
profitability claim. AI assesses catalyst strength; attribution alone does not.

A fictional EUR 500 allocation and 40 bps round-trip costs are disclosed paper
assumptions rather than unconditional blockers. These are not verified personal
fees or a statement that the broker charges EUR 0.15 per trade. Crypto remains
blocked until broker availability evidence is connected; Kraken is not Robinhood.

## Finalization

All eight responses must cite supplied evidence, match the packet, and include
the exact peer chain. Every stage must approve the paper setup without unresolved
concerns. After review, fresh data is requalified. Changed economics or substantive
source evidence reject the old review. Only expiry and retrieval timestamps can
renew when the underlying reviewed plan/evidence is unchanged.

The result is PAPER_WATCH_FOR_ENTRY or NO_ACTION. Neither opens a position or
authorizes a live trade. The metered pipeline persists artifacts, checks budget
headroom, reserves a durable setup-attempt identity before model access, and
requires refresh and delivery adapters. Lost/failed attempts are not paid-replayed.

## Deployment boundary

The scheduled collector runs the free preview. The scheduled paid job remains
disabled and has no OpenAI secret. PAPER_FINAL_VERDICTS selects the new dispatcher
when a separately authorized paid workflow is enabled. The dispatcher refreshes
provider evidence after review and delivers the signed paper archive to the
existing authenticated dashboard store and a clearly labelled paper-only Telegram
notification. UI parsing checks identity, reviewed levels, role chain and risk;
existing live actionability gates remain closed. Delivery failures never repeat
paid reviews. Synthetic integration tests cover the path; a real paid run has
not yet verified it. Resume costs only after explicit user approval.
