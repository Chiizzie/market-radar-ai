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
