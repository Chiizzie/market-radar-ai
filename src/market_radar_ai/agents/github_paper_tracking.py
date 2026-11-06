"""Dedicated CAS journal; loss or conflict never silently resets paper history."""
import base64
import json
import sqlite3
import tempfile
import time
from pathlib import Path
import requests
from .paper_tracking import PaperTracker, ingest_capture
from .paper_outcomes import Quote

BRANCH='state/paper-journal'
URL='https://api.github.com/repos/Chiizzie/market-radar-ai/contents/state/paper-journal.json'


def load(token, *, session=None, sleep=time.sleep):
    if not token: raise ValueError('paper_journal_token_required')
    transport=session or requests.Session()
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'}
    for attempt in range(3):
        try:
            response=transport.get(URL,params={'ref':BRANCH},headers=headers,timeout=(5,10),allow_redirects=False)
            if response.status_code==429 or (response.status_code==403 and getattr(response,'headers',{}).get('X-RateLimit-Remaining')=='0'):
                raise RuntimeError('paper_journal_rate_limited')
            if response.status_code in (500,502,503,504):
                raise requests.ConnectionError('temporary_read_failure')
            if response.status_code!=200: raise RuntimeError('paper_journal_read_failed')
            break
        except requests.RequestException:
            if attempt==2: raise RuntimeError('paper_journal_read_failed') from None
            sleep(attempt+1)
    envelope=response.json()
    if envelope.get('encoding')!='base64' or not 0 < envelope.get('size',1_000_000)<=750000:
        raise ValueError('paper_journal_size_or_encoding')
    state=json.loads(base64.b64decode(envelope['content'],validate=False))
    if set(state)!= {'version','decisions','observations'} or state['version']!=1:
        raise ValueError('paper_journal_format')
    return state,envelope['sha']


def restore(state, path):
    tracker=PaperTracker(path)
    for d in state['decisions']: tracker.register(d)
    for item in state['observations']:
        q=Quote.model_validate(item['quote'])
        tracker.observe(item['packet_id'],q,symbol=item['symbol'],source=item['source'],now=q.observed_at)
    return tracker


def inspect(state, *, now):
    with tempfile.TemporaryDirectory() as directory:
        return restore(state,Path(directory)/'journal.sqlite').report(now=now)


def apply(state, *, now, decision=None, capture=None, observations=()):
    with tempfile.TemporaryDirectory() as directory:
        tracker=restore(state,Path(directory)/'journal.sqlite')
        if decision is not None: tracker.register(decision)
        if capture is not None: ingest_capture(tracker,capture,now=now)
        for item in observations:
            tracker.observe_transition(item['packet_id'],Quote.model_validate(item['quote']),
                symbol=item['symbol'],source=item['source'],now=now)
        report=tracker.report(now=now)
        with sqlite3.connect(tracker.path) as db:
            decisions=tracker.decisions()
            symbols={d['packet_id']:d['plan']['symbol'] for d in decisions}
            retained=[]
            for key,body in db.execute('SELECT id,payload FROM tracked_quotes ORDER BY id,at'):
                item=json.loads(body)
                retained.append({'packet_id':key,'symbol':symbols[key], 'source':item['source'],'quote':item['quote']})
        updated={'version':1,'decisions':decisions,'observations':retained}
    return updated,report


def update(token, *, now, decision=None, capture=None, observations=(), session=None):
    """Merge immutable evidence on a fresh CAS head; never overwrite another worker.

    Only a definite 409 conflict is retried. Ambiguous writes stop this attempt;
    the next poll reads persisted state before deciding what remains to record.
    """
    transport=session or requests.Session()
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'} if token else {}
    for attempt in range(3):
        state,sha=load(token,session=transport)
        updated,report=apply(state,now=now,decision=decision,capture=capture,observations=observations)
        raw=json.dumps(updated,sort_keys=True,separators=(',',':')).encode()
        if len(raw)>750000: raise RuntimeError('paper_journal_archive_required')
        if updated==state: return report
        try:
            response=transport.put(URL,headers=headers,timeout=(5,10),allow_redirects=False,
                json={'branch':BRANCH,'sha':sha,'message':'Record paper simulation evidence',
                      'content':base64.b64encode(raw).decode()})
        except requests.RequestException:
            raise RuntimeError('paper_journal_write_unconfirmed_preserve_run_artifacts') from None
        if response.status_code==200: return report
        if response.status_code!=409: break
    raise RuntimeError('paper_journal_write_unconfirmed_preserve_run_artifacts')
