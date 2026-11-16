# Strategy research input-capacity failure — 16 November 2026

## Observed failure and impact

The 14:30, 14:35 and 14:40 Dublin scheduled scans failed solely in the new strategy-routing job. Collection, review, account sync, knowledge preparation and the other completed jobs passed in those runs. The same routing exception is verified in the 14:45 job. This is a code/input-capacity mismatch, not evidence of an Alpaca outage, spent AI allowance or missing brokerage credentials.

First failure: [43886450865 / 133366519202](https://github.com/Chiizzie/market-radar-ai/actions/runs/43886450865/job/133366519202). Reproduced capture: [43889064474 / 133375521035](https://github.com/Chiizzie/market-radar-ai/actions/runs/43889064474/job/133375521035), artifact 14235149062. Its selection manifest is **4,531,730 bytes / 5,724 symbols**, larger than the old 4,000,000-byte loader limit. The discovery trace describes the entire catalogue; the detailed capture contains only 79 stocks. The crash occurs before provider reads or strategy evaluation. The subsequent missing-artifact error is a consequence of that early crash.

## Repair

Exact runtime: `7b358fb9fd9d96e8eed77a7a86a605ae82fa453b`, based on deployed `12e7b42144b693f6ecdb86aac36b04c57c5bb694`. A dedicated manifest reader allows at most 32,000,000 bytes and the existing 20,000-symbol catalogue ceiling. It validates schema, non-authorization and unique symbol identities, reads at most the byte cap plus one, and retains every original row and prior observation. No truncation, selection change, looser trade gate or historical relabelling is introduced. Capture/news/library bounds remain unchanged.

The worker also writes a bounded health artifact on failure and re-raises the error. Upload no longer emits a second missing-artifact failure when an early input error occurs; failed work remains failed. The change does not silence error emails or make failed research look successful.

All **1,667 tests**, compilation and the unchanged frozen seven-strategy fixture check pass. Hosted [verification 43891467714](https://github.com/Chiizzie/market-radar-ai/actions/runs/43891467714) downloads the exact failed capture, reproduces the old error and proves complete row/content equality after the new read. The CLI regression uses a 6,000-symbol document exceeding 4 MB and real strategy evaluation with synthetic market inputs. No paid model calls or provider calls are made by those offline checks.

## Paper-account scheduling gap

The manual portfolio's last stored report at inspection remained seq263529 from **14 November 00:36:42 Dublin**; no scheduled manual-portfolio run was observed on 16 November. Other scheduled workflows had run. That establishes missing refreshes, not the cause of GitHub's timer behaviour.

The separate manual portfolio workflow now also follows completion of trusted main-branch scans, including scans with a failed independent job. Existing timer, manual commissioning, pinned runtime `2859eee9f35d26dcca5f010a10f9ad187d61f44e`, weekday window, concurrency, history, limits and signed research-only credential remain. First attempts from this repository's main branch are accepted; fork/branch runs are excluded. This adds no model, Telegram, market-provider or broker calls. Fresh reports are still not proof of a tradable setup or profit.

## Deployment verification

Production verification is pending in this activation commit. Record the new exact-runtime strategy result, the whole completed scan, and the refreshed manual report separately in [the receipt](../evidence/routing-capacity-repair-20261116.json). Keep the failed opening-period runs as interrupted evidence; do not backfill market decisions using later quotes. Existing paper outcomes, uncertain costs and any unresolved exposure remain intact.
