import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

class ResearchStore:
    def __init__(self, path: str = "data/market_radar_ai.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                report_json TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS decisions (
                candidate_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                decision_json TEXT NOT NULL
            )""")

    def _connect(self):
        return sqlite3.connect(self.path)

    def save_report(self, report, snapshot_id: str) -> None:
        payload = report.model_dump(mode="json")
        with self._connect() as db:
            db.execute(
                "INSERT INTO agent_reports(candidate_id,agent_id,snapshot_id,created_at,report_json) VALUES(?,?,?,?,?)",
                (report.candidate_id, report.agent_id, snapshot_id,
                 datetime.now(timezone.utc).isoformat(), json.dumps(payload))
            )
