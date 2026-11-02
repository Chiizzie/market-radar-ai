# Persistent scan rotation

Use a curated symbol file containing `{"stocks":["MSFT","AAPL"],"crypto":["XBTEUR","ETHEUR"]}`. This file is an input universe, not proof of broker eligibility. Stock symbols must match Yahoo; crypto pairs must match Kraken.

`python -m market_radar_ai.market_data.capture --universe universe.json --queue-db artifacts/scan-queue.sqlite3 --output artifacts/capture.json`

The command refreshes membership, selects up to ten stocks and five crypto pairs, then captures them with the existing checks. SQLite persists the last selection so later invocations prioritize previously deferred symbols. Selection is transactional. A provider failure still counts as a selection, allowing other symbols their turn; it never counts as successful coverage. A crash after selection can postpone those symbols until the next rotation. Keep the queue database between runs; GitHub's ephemeral workspace alone does not provide persistence.

The JSON reports queue universe/deferred counts separately from attempted capture coverage. This is fair rotation, not opportunity ranking, quote screening, automatic full-market discovery or a distributed worker lease system. Those remain subsequent integration work. No AI calls or broker orders are involved.
