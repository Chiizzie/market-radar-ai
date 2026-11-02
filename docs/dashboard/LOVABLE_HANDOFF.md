# Market Radar AI — Lovable dashboard handoff

Build a read-only dashboard for the independent `Chiizzie/market-radar-ai` project. Do not modify `Chiizzie/market-radar`, merge into main, place orders, or put API keys in frontend code. This handoff is prepared for a future Lovable project; no Lovable site or live API is deployed yet.

## Data contract and current implementation

`python -m market_radar_ai.dashboard.export --capture capture.json --output dashboard.json`

The exporter accepts version-2 captures, checks their payload hashes, recomputes freshness at export time and exposes an allowlisted snapshot. It does not pass through provider error text, secrets or arbitrary extra fields. Generated snapshots expire after 60 seconds; the frontend must independently compare its clock to `expires_at_epoch` and mark the whole view stale after expiry. A hash is an integrity check, not provider authentication. Native quote currencies remain native; display_currency EUR is a reporting preference, not proof that conversion occurred.

Use `docs/dashboard/example.json` only as a layout fixture. It intentionally contains no market observations, decisions or profit figures. GitHub's manual data-capture job uploads capture and dashboard JSON artifacts. These are development artifacts, not a browser-accessible production backend.

## Screen layout

1. Header: RESEARCH / PAPER ONLY; Europe/Dublin time; generated time; stale/offline banner; no order button.
2. Coverage: stocks first, crypto second. Show requested-symbol scope explicitly; do not label sample coverage as the entire market. Each row shows symbol, provider, source timestamp, age, currency, broker eligibility and data status.
3. Six-agent panel: opportunity discovery, technical analysis, news/catalysts, devil's advocate, risk and final decision. Until integrated, show “Not run on this capture”, not invented opinions or progress.
4. Decision detail: future entry, stop, targets, EUR risk, expiry, sourced chart annotations and debate objections. Never treat CURRENT_RESEARCH_DATA as a trade recommendation.
5. Paper outcomes: show “Not available” for null; never show a zero profit or accuracy score for missing observations.
6. AI usage: show “Not connected” for null. Later expose only aggregate settled/reserved spending and caps, not raw ledger identifiers or credentials.

Render external text as text, not raw HTML. Charts and agent output must carry source/as-of labels. No LIVE badge without a currently valid upstream snapshot.

## Connection architecture

Backend collector -> validated dashboard export -> authenticated read-only endpoint -> Lovable frontend.

The collector and model orchestration remain server-side. Store OPEN_API_KEY (mapped server-side to OPENAI_API_KEY), broker credentials and database secrets only on the backend. The browser receives a scoped read token/session where needed, never the underlying provider key. Use a narrow origin allowlist, HTTPS and server-side access checks. A client refresh cannot trigger paid model calls; model runs require the existing budget checks.

The initial interface can use the fixture while the backend endpoint is prepared. Once a Lovable project exists, supply its project URL and frontend repository so the real data client can be wired to that exact project. The current repository is the Python backend, not a ready-made Lovable frontend repository.

## Acceptance checks before connecting live data

- Empty, failed, stale and partial data states are visible.
- An expired snapshot loses any current-data indicator without waiting for a refresh.
- Stocks and crypto have independent coverage counts; deferred candidates remain visible in the future coverage contract.
- Unknown broker eligibility cannot become an actionable call.
- Null performance and spending are not converted to zero.
- No browser request contains OpenAI or broker credentials.
- Six-role decisions and outcomes are connected only after a versioned schema and provenance checks are added.

## Remaining backend milestones

Broad equity-universe discovery and symbol mapping; quote screening and ranked refresh queues; live sourced news; verified broker eligibility; EUR-normalised plans; annotated charts; real-data paper evaluation. The in-memory cache now supports repeated captures in a long-running process; it is not shared between GitHub jobs and is not a streaming feed.

## Additive coverage fields

Snapshot v1.0 now includes `coverage.stocks` and `coverage.crypto`: `universe_count`, `attempted`, `deferred`, `current`, `unusable_or_stale`, and `agent_reviewed`. Counts are checked against capture rows and optional persistent-queue metadata. Universe means the supplied or queued subset, not every listed instrument. `agent_reviewed` is zero for this capture-only exporter; a downloaded candle is not an agent review. Existing clients can ignore this additive field until their coverage cards are wired.
