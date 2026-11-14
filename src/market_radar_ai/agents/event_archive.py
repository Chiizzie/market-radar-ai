"""Bounded disk replay of validated events; preserves source order, bytes and hash."""
import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from .candidate_packages import canonical

MAX_SOURCE_BYTES = 1_000_000_000
MAX_SOURCE_EVENTS = 1_000_000


class EventArchive:
    def __init__(self, *, max_bytes=MAX_SOURCE_BYTES, max_events=MAX_SOURCE_EVENTS):
        self.directory = TemporaryDirectory(prefix='market-radar-source-')
        self.db = sqlite3.connect(str(Path(self.directory.name)/'events.sqlite'))
        self.db.execute('PRAGMA cache_size=-2048')
        self.db.execute('PRAGMA temp_store=FILE')
        self.db.execute('CREATE TABLE events(position INTEGER PRIMARY KEY, seq INTEGER NOT NULL, raw TEXT NOT NULL)')
        self.db.execute('CREATE INDEX sequence_order ON events(seq,position)')
        self.count = self.size_bytes = 0
        self.max_bytes, self.max_events = max_bytes, max_events
        self.hasher = hashlib.sha256(b'[')
        self.closed = False

    def append(self, event):
        if self.closed:
            raise ValueError('execution_archive_closed')
        raw = canonical(event)
        size = len(raw.encode())
        if self.size_bytes+size>self.max_bytes or self.count>=self.max_events:
            raise ValueError('execution_source_capacity')
        if type(event['seq']) is not int or event['seq']<0:
            raise ValueError('execution_source_sequence')
        self.db.execute('INSERT INTO events VALUES(?,?,?)', (self.count,event['seq'],raw))
        if self.count:
            self.hasher.update(b',')
        self.hasher.update(raw.encode())
        self.size_bytes += size
        self.count += 1
        if self.count%1000==0:
            self.db.commit()

    def __iter__(self):
        for (raw,) in self.db.execute('SELECT raw FROM events ORDER BY position'):
            yield json.loads(raw)

    def ordered(self):
        # Stable sort matches sorted(list, key=seq), including duplicate seqs.
        for (raw,) in self.db.execute('SELECT raw FROM events ORDER BY seq,position'):
            yield json.loads(raw)

    def __len__(self):
        return self.count

    def __eq__(self, other):
        if not isinstance(other,(list,EventArchive)):
            return NotImplemented
        return len(self)==len(other) and all(a==b for a,b in zip(self,other))

    def source_digest(self):
        h=self.hasher.copy();h.update(b']')
        return h.hexdigest()

    def close(self):
        if not self.closed:
            self.db.close();self.directory.cleanup();self.closed=True

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def __del__(self):
        if hasattr(self,'closed'):
            self.close()
