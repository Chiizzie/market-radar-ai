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


class TeamAuditStore:
    """Append-only run records; retries are idempotent and conflicts are rejected."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS team_runs (
                run_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, result_json TEXT NOT NULL)''')

    def _connect(self):
        return sqlite3.connect(self.path)

    def save(self, run_id, snapshot, result):
        from .agents.paper_team import ResearchInput, TeamResult
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError('run_id is required')
        snapshot = ResearchInput.model_validate(snapshot.model_dump())
        result = TeamResult.model_validate(result.model_dump())
        if result.snapshot_id != snapshot.digest() or result.candidate_id != snapshot.candidate_id:
            raise ValueError('Audit snapshot identity mismatch')
        payload = (snapshot.digest(), snapshot.model_dump_json(), result.model_dump_json())
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT snapshot_id,snapshot_json,result_json FROM team_runs WHERE run_id=?', (run_id,)).fetchone()
            if old is not None:
                if old != payload: raise ValueError('Run ID already contains different evidence')
                return
            db.execute('INSERT INTO team_runs VALUES(?,?,?,?)', (run_id, *payload))

    def load(self, run_id):
        from .agents.paper_team import ResearchInput, TeamResult
        with self._connect() as db:
            row = db.execute('SELECT snapshot_json,result_json FROM team_runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None: raise KeyError(run_id)
        snapshot, result = ResearchInput.model_validate_json(row[0]), TeamResult.model_validate_json(row[1])
        if snapshot.digest() != result.snapshot_id or snapshot.candidate_id != result.candidate_id:
            raise ValueError('Stored audit identity mismatch')
        return snapshot, result


def run_and_record(team, snapshot, *, run_id, store, now, plan=None):
    """Return a decision only after persistence succeeds; repeat IDs reuse saved runs."""
    try:
        saved_snapshot, saved_result = store.load(run_id)
    except KeyError:
        pass
    else:
        # Retry identity includes the snapshot; an ID cannot be reused for a new run.
        if saved_snapshot != snapshot:
            raise ValueError('Run ID snapshot conflict')
        return saved_result
    result = team.run(snapshot, now=now, plan=plan)
    store.save(run_id, snapshot, result)
    return result
