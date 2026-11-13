# Knowledge expansion and inputs for the next tests

Research reviewed **13 November 2026, Europe/Dublin**. This is the requested knowledge-first step: a content-only supplement and a practical requirements brief.

## What is now available

The [primary-source supplement](../knowledge/primary-research-supplement-20261113.json) adds **12 authored reference notes from 12 official documentation pages**, bringing the two external research collections to **24 notes**. These are research records, not 24 strategies or additional observed trades. The earlier [GitHub research bank](external-research-bank-v1.md) remains unchanged.

The new notes cover feed comparability, historical-data access, corporate actions and ticker identity, halts, filing availability, filing revisions, earnings evidence, execution delay, broker scope, itemized costs, currency routing and confidence calibration. Each separates documented facts from our engineering inference, limits and evidence needed.

**The supplement is catalogued for future use, not connected to the scheduled AI reviewer or the existing retrieval schema.** No new strategy, dependency, model call, subscription, broker order or expanded testing campaign was introduced.

## What the research changes about our priorities

| Priority | Concrete improvement to build later | Why it fits this scanner |
| --- | --- | --- |
| 1 | Retain actual fee/FX details and reconcile private Invest fills | The deployed account importer already fetches history, but drops fee detail and conversion rate. Reuse existing access before requesting exports. |
| 1 | Simulate the user's reaction time and available hours | An attractive setup that expires before a manual entry is not a usable opportunity. Keep order execution delay separate from alert response delay. |
| 2 | Verify historical feed access and preserve data identity | A wider historical feed may help research, but changing feeds must start a distinct comparison and cannot repair live-quote gaps retrospectively. |
| 2 | Add primary catalyst timestamps and observed halt status | A news label or open-session clock does not establish that a specific entry was informed and tradable. |
| 3 | Compare added knowledge on later, identical inputs | Measure whether it improves selection and outcomes before changing live selection or interpreting confidence as probability. |

This ordering is an engineering recommendation from the documentation and current repository evidence, not a finding that any change will increase profit.

### Useful discoveries

- **Existing data access can do more.** Trading 212 documents fill-level FX and fee fields, plus order origin in its [historical-order schema](https://docs.trading212.com/api/historical-events/orders_1). The pinned importer currently retains fill price, time and net/realized amounts but omits those details. Any extension must preserve private storage and reconcile gross/net totals before using them in cost models.
- **Check historical SIP before spending.** Alpaca's [FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) describes older historical SIP access without the live subscription, while its [Paper Only guidance](https://docs.alpaca.markets/us/docs/paper-trading) restricts entitlement to IEX. Account-specific historical access remains unverified. A small historical request is the next engineering check; no purchase is needed to decide whether that path works.
- **Primary sources are available.** [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and the [Nasdaq halt feed](https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS) supply useful source material. Collection, timing, coverage and failure handling still need implementation and validation.
- **Costs depend on the actual route.** [Invest currency selection](https://helpcentre.trading212.com/hc/en-us/articles/34159237080861-Can-I-choose-the-currency-in-which-to-buy-sell-assets-for-Invest-accounts) matters independently of the dashboard's USD display. Read the records first; ask about wallet use only if ambiguity remains.

## What Charlie needs to provide

| Input | Answer needed | What it determines |
| --- | --- | --- |
| Paper capital | EUR amount the simulated account should start with | Affordable positions, cash constraints and concurrent exposure; this is a modelling choice, not a request for account balance. |
| Daily loss ceiling | Maximum combined EUR loss allowed in one simulated day | A portfolio-level stop in addition to the existing per-trade limit; realized loss and open risk must be accounted for together. |
| Manual execution availability | Usual trading hours in Dublin time, and typical alert-to-order delay: under 1 minute, 1–3 minutes or over 5 minutes, or a better estimate | Which opportunities are usable and which delay scenarios should be the main benchmark. |

The existing **EUR20 maximum planned loss per trade**, intraday restriction and **no new entries at/after 22:00 Dublin** remain the starting constraints. Calendar-specific session and product restrictions may end trading earlier.

**Start with Trading 212 Invest, as already agreed.** No CFD expansion is assumed. If CFD later becomes a priority, use a separate cost/eligibility dataset; the [current API scope](https://docs.trading212.com/api/section/general-information/api-limitations) does not provide it.

No new API keys, subscription decision or initial Invest CSV is required. Existing account access and logs should be used first. No new real-money trades are needed to supply evidence for this work.

## How the next testing stage should follow

1. Turn the three user inputs into an explicit simulation specification. Define usable-entry rate, net outcome after costs, aggregate exposure/drawdown and data failures before comparing variants.
2. Verify the historical-data route and reconcile cost records. Preserve unknown or incomplete fields; do not silently assign zero costs or fill missing quotes.
3. Freeze a narrow change at a time. Keep the current baseline and original protocols; historical development comes before later untouched evaluation.
4. Compare identical future candidate inputs with existing knowledge and with selected additional notes. Implement the new schema/retrieval boundary and citation handling before any expanded AI comparison; existing budgets still apply.
5. Report outcomes by strategy, feed and session, with closed/unfilled/unresolved counts and uncertainty. Promote no claim of an edge from a few repeated alerts.

The frozen case library still contains **717 setups across only 12–13 November: 55 closed code simulations, 631 unfilled and 31 unresolved**. External reading increases available methods, not independent market history. Existing scheduled preparation may continue under its already frozen protocol; this supplement launches no additional campaign.

## Evidence checked for this brief

- Account importer: [runtime source at 3a113a4](https://github.com/Chiizzie/market-radar-ai/blob/3a113a4e8c4e03e9b28799c146db1f1cae6f987a/src/market_radar_ai/dashboard/account_sync.py), blob `54ab2ba1477a80716f8972ec142f60487cd26094`.
- [Scheduled run 43523131703](https://github.com/Chiizzie/market-radar-ai/actions/runs/43523131703): all 12 jobs succeeded after the regular session. The account job reported private sync delivery at 22:55:38 Dublin. This is operational evidence, not proof of in-session coverage or profitable decisions.
- That run's comparison log recorded three stale IEX observations and a SIP response classified `forbidden_unclassified`. The after-close observation cannot establish an in-session failure or a specific reason for the SIP refusal.
- The new material receives JSON, reference-integrity and unchanged-file checks only. Earlier 1,684-test evidence belongs to the prior code milestone; no fresh full-suite result is claimed here.

See the [content-review receipt](evidence/knowledge-inputs-review-20261113.json) for hashes, counts and scope.
