# Market Radar AI

Independent multi-agent market research and paper-trading system.

**Safety boundary:** this project has no live order execution. Broker integrations are read-only eligibility checks only. All simulated trades are recorded in the local paper ledger.

## Architecture
- Six independent specialist agents: opportunity, technical, news, devil's advocate, risk, final decision.
- Agents receive the same immutable, timestamped candidate packet and cannot see peer reports during the first pass.
- Debate starts only after all required independent reports are stored.
- Final decision is deterministic with respect to mandatory risk gates: a model cannot override a failed data-quality or risk gate.
- Charts and written levels must be generated from the same validated market snapshot.
- Qualified Telegram alerts only; no alert is sent for every raw candidate.

## Current foundation status
This is a scaffold, not a live scanner. Market-data, news, LLM, broker-catalog and Telegram adapters are interfaces/placeholders until credentials, providers and source coverage are selected and tested.

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
python -m market_radar_ai
```

Copy `.env.example` to `.env` and configure only when implementing the relevant adapters. Never commit secrets.

## Non-negotiable controls
- No write-capable broker API clients.
- No live order endpoints or order-placement code.
- Paper trading only.
- Max planned loss: EUR 20 per simulated trade.
- Intraday positions must be closed by 22:00 Europe/Dublin; no overnight intraday carry.
- Broker eligibility must be verified per instrument and direction; unsupported shorts are rejected.
- Missing, stale or contradictory data produces `NO_ACTION`.
- Model confidence is recorded but never substitutes for evidence or risk checks.

## Phase 1 data layer (in progress)

The first independent data adapters are now in `src/market_radar_ai/market_data/`:

- CoinGecko public markets discovery, quoted in EUR.
- Kraken public OHLC candles, including EUR pairs where supported by Kraken.
- Yahoo Finance historical candles through the optional `yfinance` dependency.
- A normalized instrument/candle schema, timestamp/OHLC validation, and a transparent baseline candidate ranker.
- A small connectivity command: `market-radar-data-check --crypto-limit 20`.

Install the optional Yahoo adapter with `pip install -e ".[market]"`. The project does not place orders and these feeds are research inputs, not broker execution quotes. Public data availability, rate limits, exchange pair aliases, and account-level broker eligibility must be checked at runtime. The current milestone is an adapter foundation; it is not yet a complete broad-equity universe scanner or production 15-minute pipeline.

## Run the complete offline research demo

After installing `python -m pip install -e '.[dev]'`, run:

```bash
python -m market_radar_ai.agents.offline_run --scenario objection
python -m market_radar_ai.agents.offline_run --scenario supported
```

The default objection scenario produces a rejected decision and no paper fill.
The supported scenario produces a fictional accepted plan and quote-replay outcome.
Both persist audit/budget databases and JSON reports under `artifacts/offline-demo`
(ignored by git). Repeat invocations reuse the recorded run without mock requests.
Use `--output-dir PATH` for a separate test dataset. Fixed dates, prices, broker
verification and evidence are synthetic fixtures. This is an integration demo,
not a scanner operating on current markets, an AI-performance test or a deployment.
It performs no network requests, paid inference, notifications or live orders.

### Paid pilot preparation

Store `OPENAI_API_KEY` as a GitHub Actions repository secret in
`Chiizzie/market-radar-ai`. Saving it does not enable paid requests: the model
gateway still accepts only the offline mock transport. Never commit the key.

`SpendingLedger` supports optional `monthly_limit_microeur` and
`lifetime_limit_microeur` in addition to its daily limit. Reservations count at
their full maximum until usage is settled; monthly periods use Europe/Dublin.
The lifetime limit can bound an entire pilot across days and months. These are
local application limits, not OpenAI account billing controls. All workers must
use the same persistent database and limits; a new database resets its history.
Ephemeral CI jobs must not be used for paid runs without durable budget storage.
Paid transport, token-price accounting, and durable CI budget storage remain
unimplemented; no paid connectivity test has been performed.
