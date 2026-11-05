"""Dedicated CAS journal; loss or conflict never silently resets paper history."""
import base64
import json
import sqlite3
import tempfile
from pathlib import Path
import requests
from .paper_tracking import PaperTracker, ingest_capture
from .paper_outcomes import Quote

BRANCH='state/paper-journal'
URL='https://api.github.com/repos/Chiizzie/market-radar-ai/contents/state/paper-journal.json'


def update(token, *, now, decision=None, capture=None, session=None):
    if not token: raise ValueError('paper_journal_token_required')
    transport=session or requests.Session()
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'}
    response=transport.get(URL,params={'ref':BRANCH},headers=headers,timeout=(10,30),allow_redirects=False)
    if response.status_code!=200: raise RuntimeError('paper_journal_read_failed')
    envelope=response.json()
    if envelope.get('encoding')!='base64' or envelope.get('size',1_000_000)>750000:
        raise ValueError('paper_journal_size_or_encoding')
    state=json.loads(base64.b64decode(envelope['content'],validate=False))
    if set(state)!= {'version','decisions','observations'} or state['version']!=1:
        raise ValueError('paper_journal_format')
    with tempfile.TemporaryDirectory() as directory:
        tracker=PaperTracker(Path(directory)/'journal.sqlite')
        for d in state['decisions']: tracker.register(d)
        for item in state['observations']:
            q=Quote.model_validate(item['quote'])
            tracker.observe(item['packet_id'],q,symbol=item['symbol'],source=item['source'],now=q.observed_at)
        if decision is not None: tracker.register(decision)
        if capture is not None: ingest_capture(tracker,capture,now=now)
        report=tracker.report(now=now)
        with sqlite3.connect(tracker.path) as db:
            decisions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM tracked_plans ORDER BY id')]
            symbols={d['packet_id']:d['plan']['symbol'] for d in decisions}
            observations=[]
            for key,body in db.execute('SELECT id,payload FROM tracked_quotes ORDER BY id,at'):
                item=json.loads(body)
                observations.append({'packet_id':key,'symbol':symbols[key], 'source':item['source'],'quote':item['quote']})
        updated={'version':1,'decisions':decisions,'observations':observations}
    raw=json.dumps(updated,sort_keys=True,separators=(',',':')).encode()
    if len(raw)>750000: raise RuntimeError('paper_journal_archive_required')
    if updated!=state:
        response=transport.put(URL,headers=headers,timeout=(10,30),allow_redirects=False,
            json={'branch':BRANCH,'sha':envelope['sha'],'message':'Record paper simulation evidence',
                  'content':base64.b64encode(raw).decode()})
        if response.status_code!=200:
            raise RuntimeError('paper_journal_write_unconfirmed_preserve_run_artifacts')
    return report
