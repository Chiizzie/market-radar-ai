"""Authenticated cache of an immutable, fully validated research-event prefix.

The signed storage service remains authoritative. A cache never supplies a
current-health result: workers must still read the durable tail before acting.
"""
import gzip
import hashlib
import hmac
import json
import os
from pathlib import Path

MAX_BYTES = 75_000_000
MAX_EVENTS = 100_000
DOMAIN = b'market-radar-research-prefix-v1\0'


class ResearchCheckpoint:
    def __init__(self, root, *, experiment, day, secret):
        if not isinstance(secret, str) or len(secret) < 32:
            raise ValueError('checkpoint_secret_required')
        self.path = Path(root) / f'{experiment}-{day}.cache'
        self.experiment, self.day, self.key = experiment, day, secret.encode()

    def _signature(self, metadata):
        raw = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
        return hmac.new(self.key, DOMAIN + raw, hashlib.sha256).hexdigest()

    def restore(self, apply):
        if not self.path.exists():
            return 0
        # A malformed cache is discarded, never used as evidence. Replay from
        # storage is safe; malformed authoritative events still fail the worker.
        try:
            if self.path.stat().st_size > MAX_BYTES + 65536:
                raise ValueError('checkpoint_size')
            with self.path.open('rb') as f:
                header = f.readline(4097)
                if len(header) > 4096 or not header.endswith(b'\n'):
                    raise ValueError('checkpoint_header')
                manifest = json.loads(header)
                metadata, signature = manifest['metadata'], manifest['signature']
                if not hmac.compare_digest(self._signature(metadata), signature):
                    raise ValueError('checkpoint_signature')
                if (metadata['version'] != 1 or metadata['experiment'] != self.experiment
                        or metadata['day'] != self.day):
                    raise ValueError('checkpoint_partition')
                with gzip.GzipFile(fileobj=f) as packed:
                    raw = packed.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != metadata['sha256']:
                    raise ValueError('checkpoint_digest')
            rows = [json.loads(line) for line in raw.splitlines()]
            if not rows or len(rows) != metadata['events'] or len(rows) > MAX_EVENTS:
                raise ValueError('checkpoint_count')
            cursor, ids = 0, set()
            for row in rows:
                if (type(row['seq']) is not int or row['seq'] <= cursor
                        or row['experiment_id'] != self.experiment or row['day'] != self.day
                        or row['event_id'] in ids):
                    raise ValueError('checkpoint_order_or_scope')
                cursor = row['seq']; ids.add(row['event_id'])
            if cursor != metadata['cursor']:
                raise ValueError('checkpoint_cursor')
        except (ValueError, KeyError, TypeError, OSError, EOFError):
            return 0
        # All bytes and boundaries are authenticated before mutating projection.
        # Domain validation remains identical to a fresh storage replay.
        for row in rows:
            apply(row)
        return cursor

    def save(self, journal, cursor):
        if not cursor or not journal.exists() or journal.stat().st_size > MAX_BYTES:
            return
        raw = journal.read_bytes()
        count = raw.count(b'\n')
        if not count or count > MAX_EVENTS:
            return
        metadata = {'version': 1, 'experiment': self.experiment, 'day': self.day,
                    'cursor': cursor, 'events': count, 'sha256': hashlib.sha256(raw).hexdigest()}
        header = json.dumps({'metadata': metadata, 'signature': self._signature(metadata)},
                            sort_keys=True, separators=(',', ':')).encode() + b'\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('wb') as f:
            os.chmod(temporary, 0o600)
            f.write(header)
            with gzip.GzipFile(fileobj=f, mode='wb', compresslevel=1, mtime=0) as packed:
                packed.write(raw)
        os.replace(temporary, self.path)


def configured_checkpoint(client, experiment, day):
    root = os.environ.get('RESEARCH_EVENT_CHECKPOINT_DIR')
    if not root:
        return None
    return ResearchCheckpoint(root, experiment=experiment, day=day, secret=client.secret)
