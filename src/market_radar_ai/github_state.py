"""Read-your-confirmed-write support for append-only GitHub state ledgers.

The cached blob is usable only after an acknowledged write. Every subsequent
write still uses GitHub's compare-and-swap SHA, including after a conflict.
"""
from copy import deepcopy
from hashlib import sha1
from uuid import uuid4


class LedgerConflict(RuntimeError):
    """A definitive HTTP 409: re-read and re-evaluate, never repeat a side effect."""


class StaleLedgerRead(ValueError):
    pass


def fresh_params(branch):
    return {'ref': branch, 'cache_bust': uuid4().hex}


class ConfirmedWrites:
    def __init__(self):
        self.pending = None
        self.floor = None

    def take(self):
        result, self.pending = self.pending, None
        return deepcopy(result)

    def accept(self, state):
        if self.floor is not None:
            if {k:v for k,v in state.items() if k!='entries'} != {k:v for k,v in self.floor.items() if k!='entries'}:
                raise StaleLedgerRead('ledger_configuration_changed')
            for key, before in self.floor['entries'].items():
                after = state['entries'].get(key)
                if after is None:
                    raise StaleLedgerRead('ledger_read_missing_confirmed_entry')
                if 'actual' in before:
                    if (before['day'] != after['day'] or before['reserved'] != after['reserved']
                            or before['actual'] is not None and before != after):
                        raise StaleLedgerRead('ledger_read_regressed')
                elif before['state'] == 'confirmed' and before != after:
                    raise StaleLedgerRead('ledger_read_regressed')
        self.floor = deepcopy(state)

    def remember(self, state, raw):
        self.accept(state)
        blob_sha = sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.pending = (deepcopy(state), blob_sha)
