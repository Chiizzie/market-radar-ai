"""Durable offline debate lifecycle. Unfinished runs cannot be silently retried."""
import json
import sqlite3
from pathlib import Path
from hashlib import sha256
from .debate import DebateOutcome
from .paper_team import PaperPlan


class DebateStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS debate_runs (
                id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                request_json TEXT NOT NULL, state TEXT NOT NULL,
                result_json TEXT, failure TEXT)''')

    def begin(self, run_id, request):
        if not isinstance(run_id, str) or not run_id.strip(): raise ValueError('run_id required')
        payload = json.dumps(request, sort_keys=True, separators=(',', ':'))
        digest = sha256(payload.encode()).hexdigest()
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT request_hash,state,result_json FROM debate_runs WHERE id=?',(run_id,)).fetchone()
            if row:
                if row[0] != digest: raise ValueError('Run ID request conflict')
                if row[1] != 'completed': raise RuntimeError('Run unfinished or failed; inspect before a new run')
                return json.loads(row[2])
            db.execute('INSERT INTO debate_runs VALUES(?,?,?,\'running\',NULL,NULL)',(run_id,digest,payload))
        return None

    def finish(self, run_id, result):
        payload = json.dumps(result, sort_keys=True)
        with sqlite3.connect(self.path) as db:
            cursor = db.execute('UPDATE debate_runs SET state=\'completed\',result_json=? WHERE id=? AND state=\'running\'',(payload,run_id))
            if cursor.rowcount != 1: raise ValueError('Run is not running')

    def fail(self, run_id):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE debate_runs SET state=\'failed\',failure=\'execution_or_persistence_failure\' WHERE id=? AND state=\'running\'',(run_id,))

    def inspect(self, run_id):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT request_json,state,result_json,failure FROM debate_runs WHERE id=?',(run_id,)).fetchone()
        if row is None: raise KeyError(run_id)
        return {'request':json.loads(row[0]), 'state':row[1],
                'result':json.loads(row[2]) if row[2] else None,'failure':row[3]}


def run_recorded_debate(coordinator, snapshot, *, plan, run_id, now, store,
                        maximum_microeur=10):
    """Same run ID means historical retrieval, not fresh trading authorization."""
    request = {'snapshot':snapshot.model_dump(mode='json'),
               'plan':plan.model_dump(mode='json'), 'now':now.isoformat(),
               'maximum_microeur':maximum_microeur}
    cached = store.begin(run_id, request)
    if cached is not None:
        return DebateOutcome.model_validate(cached['debate']), PaperPlan.model_validate(cached['plan']) if cached['plan'] else None
    try:
        outcome, accepted = coordinator.run_paper(snapshot, plan=plan, run_id=run_id,
            now=now, maximum_microeur=maximum_microeur)
        store.finish(run_id, {'debate':outcome.model_dump(mode='json'),
                             'plan':accepted.model_dump(mode='json') if accepted else None})
        return outcome, accepted
    except Exception:
        store.fail(run_id)
        raise
