"""Authenticated acceleration of a validated immutable database prefix.

The checkpoint contains raw server events, never a pickled/SQL projection or new
quotes. A domain-separated HMAC binds the compressed bytes, partition, cursor
and count. Consumers rebuild with the normal event validators, then read the
authoritative server tail before observing. Invalid caches fall back to a cold
read. No event timestamp, receipt, ordering or outcome rule is changed.
"""
import gzip
import hashlib
import hmac
import json
import os
import time
import zlib
from pathlib import Path
from .candidate_packages import canonical
from .comparison_live import KINDS, event_id

VERSION = 'comparison-prefix-v1'
MAX_BYTES = 256_000_000
MAX_EVENTS = 300000
MAX_LINE = 2_000_000


def signature(secret, manifest):
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError('checkpoint_secret_required')
    return hmac.new(secret.encode(), (VERSION+'\n'+canonical(manifest)).encode(), hashlib.sha256).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('checkpoint_capacity')
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(worker, directory, secret):
    """Seal only a fully synchronized prefix; the cache is never authoritative."""
    source = worker.root/'comparison-events.jsonl'
    if not source.is_file() or not worker.cursor:
        return False
    root = Path(directory); root.mkdir(parents=True, exist_ok=True)
    temp = root/'events.jsonl.gz.tmp'
    cursor = count = size = 0
    with source.open('rb') as src, gzip.open(temp, 'wb', compresslevel=1) as out:
        for line in src:
            size += len(line); count += 1
            if size > MAX_BYTES or count > MAX_EVENTS or len(line) > MAX_LINE:
                raise ValueError('checkpoint_capacity')
            event = json.loads(line)
            if (type(event['seq']) is not int or event['seq'] <= cursor
                    or event['event_id'] not in worker.seen
                    or event['event_id'] != event_id(worker.experiment, event)
                    or event['experiment_id'] != worker.experiment or event['day'] != worker.day):
                raise ValueError('checkpoint_source_invalid')
            cursor = event['seq']; out.write(line)
    if cursor != worker.cursor or count != len(worker.seen):
        raise ValueError('checkpoint_prefix_mismatch')
    manifest = {'version': VERSION, 'experiment': worker.experiment, 'day': worker.day,
                'cursor': cursor, 'count': count, 'bytes': size, 'sha256': file_hash(temp)}
    meta = root/'manifest.json.tmp'
    meta.write_text(canonical({'manifest': manifest, 'hmac': signature(secret, manifest)})+'\n')
    os.replace(temp, root/'events.jsonl.gz')
    os.replace(meta, root/'manifest.json')
    return True


def restore(worker, directory, secret):
    """Fresh disposable projection only; transaction rollback on bad content."""
    started = time.monotonic()
    if worker.cursor or worker.seen or (worker.root/'comparison-events.jsonl').exists():
        raise ValueError('fresh_checkpoint_projection_required')
    root = Path(directory)
    temp = worker.root/'checkpoint-restore.jsonl.tmp'
    state = 'miss'
    try:
        path = root/'manifest.json'
        if not path.is_file():
            return False
        state = 'rejected'
        if path.stat().st_size > 4096:
            raise ValueError('checkpoint_manifest_capacity')
        sealed = json.loads(path.read_text()); m = sealed['manifest']
        if (not hmac.compare_digest(sealed['hmac'], signature(secret,m))
                or m['version'] != VERSION or m['experiment'] != worker.experiment or m['day'] != worker.day
                or type(m['count']) is not int or not 0 < m['count'] <= MAX_EVENTS
                or type(m['bytes']) is not int or not 0 < m['bytes'] <= MAX_BYTES
                or type(m['cursor']) is not int or m['cursor'] <= 0
                or file_hash(root/'events.jsonl.gz') != m['sha256']):
            raise ValueError('checkpoint_binding_invalid')
        seen = set(); cursor = size = 0
        with worker.store.replay_batch():
            with gzip.open(root/'events.jsonl.gz','rb') as src, temp.open('wb') as out:
                while line := src.readline(MAX_LINE+1):
                    size += len(line)
                    if len(line) > MAX_LINE or size > m['bytes'] or len(seen) >= m['count']:
                        raise ValueError('checkpoint_capacity')
                    event = json.loads(line)
                    if (type(event['seq']) is not int or event['seq'] <= cursor
                            or event['experiment_id'] != worker.experiment or event['day'] != worker.day
                            or event['kind'] not in KINDS or event['event_id'] in seen
                            or event_id(worker.experiment,event) != event['event_id']):
                        raise ValueError('checkpoint_event_invalid')
                    worker.apply_payload(worker.store,event)
                    seen.add(event['event_id']); cursor = event['seq']; out.write(line)
            if cursor != m['cursor'] or len(seen) != m['count'] or size != m['bytes']:
                raise ValueError('checkpoint_prefix_mismatch')
    except (ValueError, KeyError, TypeError, EOFError, OSError, zlib.error):
        return False
    else:
        os.replace(temp, worker.root/'comparison-events.jsonl')
        worker.cursor = cursor; worker.seen = seen
        state = 'restored'
        worker.health['checkpoint_events'] = len(seen)
        worker.health['checkpoint_cursor'] = cursor
        return True
    finally:
        temp.unlink(missing_ok=True)
        worker.health['checkpoint_state'] = state
        worker.health['checkpoint_seconds'] = round(time.monotonic()-started,3)
