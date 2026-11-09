# Conditional paper review policy — 9 November 2026

The scanner could qualify a pre-trigger plan while reviewers demanded post-trigger confirmation; completed reviews could also be invalidated merely by a new volume ratio. Policy `paper-specialists-v3-conditional-chief` separates conditional approval from observed entry and preserves the reviewed plan through fresh safety checks.

## Changes

- Specialists may approve a conditional plan before its trigger. The watcher must still observe an eligible entry after approval. The chief can resolve analytical uncertainty, but any explicit REJECT remains a veto. Legacy decisions retain their original unanimous-review contract.
- Stock continuation and pullback strategies use a minimum recent/baseline volume ratio of 1.0 and a completed bounded news-risk check. They do not require a fresh positive headline. Opening-range and crypto rules are unchanged; the 15-minute opening experiment remains shadow-only.
- Review deadlines and initial expiry are 180 seconds. A refreshed watch is bounded by 180 seconds after validation and 360 seconds after assembly, plus existing evidence/session cutoffs. The post-approval polling bridge lasts 185 seconds. Stock refresh does not fetch unrelated crypto.
- Revalidation freezes entry, stop, targets, quantity and costs. It checks fresh quotes, FX, session, catalogue, trend, support, completed-bar integrity, news/calendar changes and EUR risk. Falling initial selection volume alone no longer cancels a reviewed plan. Material news changes still require reassessment.
- New-policy entries and forward comparisons cap spread and entry overshoot at 20 basis points. Planned loss remains capped at EUR 20; actual gap losses can still exceed planned losses.
- New comparison protocol `abfaa5c8b4fd3e76a46dddd142bd4747765b32c0caf2c6122afe9dbff6c7e4e8` isolates these changes from historical results. Historical six stopped simulations and their approximately EUR 60.40 loss are not rewritten or certified as accurate executions by this change.
- Paper only. AI budgets, broker restrictions, intraday cutoffs and the original scanner are unchanged.

## Historical admission replay

`scripts/replay_qualification_day.py` replays archived captures at their original evaluation times, without paid AI calls or future market information. Of 78 scheduled runs examined, 77 capture artifacts were available and 76 contained usable replay inputs. Run 42697506679 lacked the required capture/qualification inputs. Per-run input hashes and results are in `2026-11-09-policy-replay.json`.

Original admission rules yielded 40 eligible stock observations across 19 symbols. Revised rules yielded 119 across 50 symbols. Repeated observations are not independent setups, executed trades, AI approvals or profits. This session informed the changes and is not an out-of-sample performance test. The APLD example still fails material-news revalidation despite removal of the volume-only veto.

## Validation and remaining evidence

Backend: 1,362 tests passed. Dashboard: 46 focused tests passed and production build succeeded. Tests cover legacy compatibility, signed decision ingestion, chief uncertainty resolution, hard vetoes, bounded expiry, frozen plans and fresh safety failures.

The compatible dashboard was published before the scanner contract switch. Regular-session forward validation is still required: observe actual conditional approval, entry, exit and comparison outcomes under the new protocol. This release establishes no profitability claim. Historical quote/FX anomalies require independent raw-evidence verification. Missing/gapped provider charts and spending limits can still prevent a review; these are not waived to manufacture alerts.
