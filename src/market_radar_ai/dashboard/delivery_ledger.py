"""Durable, fail-closed notification reservations on a separate GitHub state branch.

A reservation is permanent even when delivery is uncertain. Never retry a send
because its acknowledgement or settlement was lost.
"""
import base64
import json
import re
import time
import requests
from ..github_state import ConfirmedWrites, LedgerConflict, StaleLedgerRead, fresh_params

BRANCH = 'state/research-notifications'
PATH = 'state/research-notifications.json'
URL = 'https://api.github.com/repos/Chiizzie/market-radar-ai/contents/' + PATH


def initial_state():
    return {'version': 1, 'entries': {}}


def validate(raw):
    if (not isinstance(raw, dict) or set(raw) != {'version', 'entries'}
            or type(raw['version']) is not int or raw['version'] != 1
            or not isinstance(raw['entries'], dict)):
        raise ValueError('invalid_delivery_ledger')
    for key, row in raw['entries'].items():
        if (not re.fullmatch(r'research:[a-f0-9]{64}', key)
                or not isinstance(row, dict) or set(row) != {'state'}
                or row['state'] not in ('reserved', 'confirmed')):
            raise ValueError('invalid_delivery_record')
    return raw


class GitHubDeliveryStore:
    def __init__(self, token, *, session=None):
        if not token:
            raise ValueError('github_token_required')
        self.session = session or requests
        self.headers = {'Authorization': 'Bearer ' + token,
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28', 'Cache-Control':'no-cache'}
        self._confirmed = ConfirmedWrites()

    def load(self):
        cached = self._confirmed.take()
        if cached is not None: return cached
        for attempt in range(3):
            try:
                return self._load()
            except StaleLedgerRead:
                if attempt == 2:
                    raise RuntimeError('Delivery ledger stale read; sending disabled') from None
                time.sleep(.2 * (attempt + 1))

    def _load(self):
        try:
            response = self.session.get(URL, params=fresh_params(BRANCH),
                headers=self.headers, timeout=(10, 30), allow_redirects=False)
            if response.status_code != 200:
                raise ValueError()
            data = response.json()
            if data['encoding'] != 'base64' or not 0 < data['size'] <= 500000:
                raise ValueError()
            sha = data['sha']
            if not re.fullmatch(r'[a-f0-9]{40}', sha):
                raise ValueError()
            state = validate(json.loads(base64.b64decode(data['content'])))
            self._confirmed.accept(state)
            return state, sha
        except StaleLedgerRead:
            raise
        except Exception:
            raise RuntimeError('Delivery ledger unavailable; sending disabled') from None

    def save(self, state, expected_sha):
        raw = json.dumps(validate(state), sort_keys=True).encode()
        if len(raw) > 500000 or not re.fullmatch(r'[a-f0-9]{40}', expected_sha):
            raise ValueError('delivery_ledger_write_invalid')
        try:
            response = self.session.put(URL, headers=self.headers,
                timeout=(10, 30), allow_redirects=False,
                json={'branch': BRANCH, 'sha': expected_sha,
                      'message': 'Record research notification delivery state',
                      'content': base64.b64encode(raw).decode()})
        except Exception:
            raise RuntimeError('Delivery ledger write unconfirmed; do not send or retry') from None
        if response.status_code == 409:
            raise LedgerConflict('Delivery ledger conflict [http_409]; do not send or retry without fresh state')
        if response.status_code != 200:
            raise RuntimeError(f'Delivery ledger write unconfirmed [http_{int(response.status_code)}]; do not send or retry')
        self._confirmed.remember(state, raw)


class DeliveryLedger:
    def __init__(self, store):
        self.store = store

    def reserve(self, key):
        for attempt in range(3):
            try: return self._reserve(key)
            except LedgerConflict:
                if attempt == 2: raise
                time.sleep(.2 * (attempt + 1))

    def _reserve(self, key):
        validate({'version': 1, 'entries': {key: {'state': 'reserved'}}})
        state, sha = self.store.load()
        validate(state)
        if key in state['entries']:
            raise ValueError('delivery_already_attempted_do_not_retry')
        state['entries'][key] = {'state': 'reserved'}
        self.store.save(state, sha)

    def confirm(self, key):
        for attempt in range(3):
            try: return self._confirm(key)
            except LedgerConflict:
                if attempt == 2: raise
                time.sleep(.2 * (attempt + 1))

    def _confirm(self, key):
        state, sha = self.store.load()
        validate(state)
        if key not in state['entries']:
            raise ValueError('delivery_not_reserved')
        if state['entries'][key]['state'] == 'confirmed':
            return
        state['entries'][key]['state'] = 'confirmed'
        self.store.save(state, sha)
