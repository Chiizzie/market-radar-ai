# Existing skills reviewed for Market Radar — 12 November 2026

The existing custom `market-radar-evidence` skill remains the scanner-specific audit workflow. Downloaded skills are development/research instructions; installing them in ChatGPT does not add capabilities to the deployed six-role scanner unless we deliberately implement and test runtime changes.

## Sources and fixed revisions

- OpenAI curated skills: https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated
- Alpaca official skills: https://github.com/alpacahq/alpaca-skills/tree/0e7c35163ae462730de1f4a0bfafceac82b7d59b
- Broader community catalogues were searched for discovery; their security/profitability labels were not accepted as independent verification.

No external skill was installed or granted account access by this scan. Review depth is stated below; this is not a blanket security certification of either repository or its dependencies.

## Useful shortlist

| Skill | Benefit for this project | Fit and review result |
| --- | --- | --- |
| [Alpaca trading backtest](https://github.com/alpacahq/alpaca-skills/tree/0e7c35163ae462730de1f4a0bfafceac82b7d59b/skills/trading-api/backtest) | Explicit strategy definitions, saved inputs/code, reproducible comparisons, fees and unseen-period checks | **Best research candidate, with amendments.** Read the whole SKILL and companion reference. It requires Alpaca CLI and authenticated data access. No bundled executable scripts in this skill. See the fill-rule issues below before adoption. |
| [Alpaca reconciliation/idempotency](https://github.com/alpacahq/alpaca-skills/tree/0e7c35163ae462730de1f4a0bfafceac82b7d59b/skills/broker-api/reconciliation-idempotency) | Persist intent before sending, reconcile missing responses, deduplicate observations, handle corrections | **Useful engineering reference.** Read the whole SKILL and companion reference. It targets the institutional Broker API and refers to other integration/funding/event skills. Its endpoints/auth are not drop-in retail Trading API instructions. Apply principles, verify exact Trading API schemas separately. |
| [OpenAI security-best-practices](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/security-best-practices) | Review credentials, dashboard access, dependency and application security before broker activation | **Good security-review candidate.** Main instructions and package inventory reviewed; the extensive framework reference collection has not received a full package audit. It triggers on an explicit security task; it is not a strategy reviewer. |
| [OpenAI security-threat-model](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/security-threat-model) | Map broker keys, model output, dashboard users and order-worker trust boundaries | **Useful before execution rollout.** Main instructions reviewed in the preceding work session; companion references/dependencies remain to be reviewed before installation. |
| [OpenAI Playwright](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/playwright) | Reproduce dashboard flows, inspect missing opportunity/entry/exit information, collect browser traces | **Useful for UI verification.** Read SKILL, both references and the complete wrapper script. The wrapper invokes `npx --yes --package @playwright/cli` without a version pin. Pin/review that dependency and use the available browser integration where appropriate before running it. It does not itself provide a permanent automated regression suite. |
| [OpenAI gh-fix-ci](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/gh-fix-ci) | Diagnose failed PR checks and collect actionable logs | **Secondary fit.** Main instructions reviewed; bundled script is not fully audited by this scan. It is PR/`gh`-CLI oriented, whereas our recurring incidents occur in scheduled workflows already covered by the custom skill. |

Alpaca also publishes paper-trading workflows. The catalogue and file inventory were inspected, but their substantial individual instructions were not fully audited here; they are **discovered candidates**, not installed/vetted trading agents.

## Specific amendments needed for the backtest candidate

The reviewed Alpaca reference has a buy-limit fill example which takes the minimum of bar open and limit, then adds price friction. That arithmetic can produce a fill **above the buy limit**. The symmetric sell example can violate its minimum price. A limit-respecting simulator must separate fees from execution price, cap permissible fills, and leave an order unfilled when its price condition cannot be demonstrated.

It also permits the most recent earlier quote when an exact timestamp is unavailable without prescribing a maximum quote age. Our existing missing/stale/spread checks must remain explicit. Its time-based fallback to the nearest session bar must not select future data to justify an earlier execution. Record missing observations instead of silently filling across gaps.

Keep the useful elements: immutable strategy definitions, signal/fill separation, raw data fingerprints, chronological unseen periods, explicit feed/adjustment policy, realistic costs and complete artifacts. Do not tune a rule repeatedly on the same missed moves and call the result out-of-sample evidence.

The Alpaca repository uses Apache License 2.0; preserve the license and attribution if adapting/distributing its content. Installation examples include moving `@latest` CLI versions and broad local permissions. Pin the actual CLI/dependency revision and use only the minimum data/account scope for the task.

## Recommended order

1. Adopt a narrowly adapted backtest workflow for predeclared strategy comparisons, with the corrections above and our existing evidence requirements.
2. Use a dedicated security/threat review when persistent paper execution and its credential boundary are ready.
3. Add browser-flow checks for the dashboard's entry/exit/status views.
4. Keep scheduled-run diagnosis in the existing custom scanner workflow; add the PR-specific CI helper only when it adds value.

None of these is evidence of trading edge, a source of verified successful-trader signals, or permission to place live orders. Broker engineering, research validity and prospective performance remain separate acceptance tracks.
