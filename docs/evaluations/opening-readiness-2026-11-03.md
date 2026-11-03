# Opening readiness and live crypto rehearsal — 2026-11-03

Code: 1b8450f215cd396f093d6f8609a8d55ec4be8eda
Repository: Chiizzie/market-radar-ai
Branch: phase-1/market-data-layer

Full local suite: 685 passed.
GitHub full suite: 685 passed in job 126255108613.
CI run: https://github.com/Chiizzie/market-radar-ai/actions/runs/41733063086

Live run: https://github.com/Chiizzie/market-radar-ai/actions/runs/41733195736
Result: SUCCESS, 46 seconds; paid_analysis=false, candidate_market=crypto,
send_candidate_review=false, send_snapshot=true.

Observed results at approximately 22:43 Dublin:
- Alpaca IEX returned bars for all eight requested stocks. Artifact provider
  fields confirm alpaca_iex. All eight were correctly stale after cash close.
- Kraken returned completed candles for all four crypto pairs and all four
  passed freshness/quality checks.
- Public EUR reference quotes validated for XBTEUR, ETHEUR, SOLEUR, XRPEUR.
- Readiness mode AFTER_CUTOFF_RESEARCH_ONLY; no permitted entry window.
- Current shortlisted research packages: XRP and SOL. Neither had linked news
  in this bounded capture. Missing evidence was retained, not filled by inference.
- Deterministic replay rejected both packages at their original expiry and
  rejected every original candle capture after a simulated 16-minute delay.
  These are guard tests, not future live observations or paper-trade outcomes.
- Downloaded readiness and package-batch JSON reproduced exactly under canonical
  JSON comparison at their original recorded check times.
- Candidate review state ready_dry_run, candidate crypto:XRPEUR, model_calls=0.
- Dashboard snapshot delivery confirmed:
  3083803e89aa90e12de41aaf55a059d324f042614a4999262075374ce2a224b7
  generated 2026-11-03T22:43:36.974620+00:00.
- No paid model call, order, paper position or performance result was created.

Artifact ID: 13276662635
ZIP SHA-256: c9a76326954a8efa83cc2579b44be03a902bf59746af8043cadce114e1cadf7f
Artifact downloaded and checksum verified. Evidence expires normally.

See ../market-captures/OPENING_READINESS.md for the manual runbook, the current
20-bar/100-minute stock warm-up, provider limitations and remaining paper-call
gates. No automatic tomorrow dispatch or recurring schedule was created.
