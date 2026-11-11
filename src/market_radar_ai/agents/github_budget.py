"""Small compare-and-swap ledger on a dedicated branch; never silently reinitializes."""
import base64
import json
import re
import time
from datetime import date
from threading import RLock
from zoneinfo import ZoneInfo
from typing import Literal
import requests
from pydantic import BaseModel, ConfigDict, Field

REPOSITORY = 'Chiizzie/market-radar-ai'
BRANCH = 'state/ai-budget'
PATH = 'state/ai-budget.json'
URL = f'https://api.github.com/repos/{REPOSITORY}/contents/{PATH}'
LIMITS = {'daily':1000000, 'monthly':10000000, 'lifetime':100000000}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Usage(Strict):
    response_id: str | None
    model: str | None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    cost_usd: str
    eur_per_usd: str
    pricing_checked: Literal['2026-11-02']


class Entry(Strict):
    day: str
    reserved: int = Field(gt=0)
    actual: int | None = Field(default=None, ge=0)
    usage: Usage | None = None


class State(Strict):
    version: Literal[1]
    currency: Literal['EUR']
    limits_microeur: dict[str, int]
    entries: dict[str, Entry]


def initial_state():
    return {'version':1, 'currency':'EUR', 'limits_microeur':dict(LIMITS), 'entries':{}}


def validate_state(raw):
    state = State.model_validate(raw)
    if state.limits_microeur != LIMITS:
        raise ValueError('Budget configuration mismatch')
    for key, entry in state.entries.items():
        if not re.fullmatch(r'[a-zA-Z0-9:_-]{1,160}', key):
            raise ValueError('Invalid request identity')
        if date.fromisoformat(entry.day).isoformat() != entry.day:
            raise ValueError('Invalid budget day')
    return state.model_dump(mode='json')


class GitHubBudgetStore:
    """Only this project's dedicated state path can be read or written."""
    def __init__(self, token):
        if not token:
            raise ValueError('GitHub token required')
        self._headers = {'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
                         'X-GitHub-Api-Version':'2022-11-28'}

    def load(self):
        # Only idempotent reads may retry. Never retry a write or an AI call.
        reason = 'transport_unavailable'
        for attempt in range(3):
            response = None
            delay = attempt + 1
            try:
                response = requests.get(URL, params={'ref':BRANCH}, headers=self._headers,
                                        timeout=(10,30), allow_redirects=False)
            except requests.RequestException:
                reason = 'transport_unavailable'
            else:
                code = response.status_code
                if code == 200:
                    try:
                        data = response.json()
                        if data['encoding'] != 'base64' or data['size'] > 500000:
                            raise ValueError('Invalid budget file')
                        state = json.loads(base64.b64decode(data['content']))
                        sha = data['sha']
                        if not re.fullmatch(r'[0-9a-f]{40}', sha):
                            raise ValueError('Invalid budget version')
                        return validate_state(state), sha
                    except Exception:
                        # Corruption/configuration changes must not be hidden by retries.
                        raise RuntimeError('Budget read failed [invalid_payload]; paid calls disabled') from None
                reason = f'http_{code}'
                retry_after = (getattr(response, 'headers', {}) or {}).get('Retry-After')
                short_retry = (isinstance(retry_after,str) and retry_after.isdigit()
                               and int(retry_after)<=5)
                if code not in (429,500,502,503,504) and not (code==403 and short_retry):
                    break
                if retry_after is not None:
                    if not short_retry:break
                    delay=max(1,int(retry_after))
            if attempt<2:
                time.sleep(delay)
        # Only an allowlisted reason code is logged, never headers or server bodies.
        raise RuntimeError(f'Budget read failed [{reason}]; paid calls disabled') from None

    def save(self, state, expected_sha):
        state = validate_state(state)
        raw = json.dumps(state, sort_keys=True, indent=2).encode()
        if len(raw) > 500000:
            raise RuntimeError('Budget record needs maintenance; paid calls disabled')
        try:
            response = requests.put(URL, headers=self._headers, timeout=(10,30),
                allow_redirects=False, json={'branch':BRANCH, 'sha':expected_sha,
                    'message':'Record AI budget reservation or settlement',
                    'content':base64.b64encode(raw).decode()})
            if response.status_code != 200:
                raise ValueError('Conflict or failed write')
        except Exception:
            # Even if the write succeeded but the reply was lost, DO NOT call OpenAI.
            raise RuntimeError('Budget write unconfirmed; paid calls disabled') from None


class GitHubSpendingLedger:
    limit = LIMITS['daily']
    monthly_limit = LIMITS['monthly']
    lifetime_limit = LIMITS['lifetime']

    def __init__(self, store):
        self.store = store
        # Forked model clients share this ledger. Serialize each entire read +
        # CAS write transaction, not their provider calls. Cross-process races
        # still fail closed through the existing remote compare-and-swap check.
        self._lock = RLock()

    def reserve(self, request_id, maximum_microeur, now):
        with self._lock:
            return self._reserve(request_id, maximum_microeur, now)

    def _reserve(self, request_id, maximum_microeur, now):
        if (not re.fullmatch(r'[a-zA-Z0-9:_-]{1,160}', request_id)
                or now.tzinfo is None or now.utcoffset() is None
                or type(maximum_microeur) is not int or maximum_microeur <= 0):
            raise ValueError('Invalid reservation')
        state, sha = self.store.load()
        state = validate_state(state)
        if request_id in state['entries']:
            raise ValueError('Request ID already reserved; inspect before retry')
        day = now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
        for period, limit in state['limits_microeur'].items():
            entries = [e for e in state['entries'].values() if period == 'lifetime'
                       or (period == 'daily' and e['day'] == day)
                       or (period == 'monthly' and e['day'][:7] == day[:7])]
            total = sum(e['reserved'] if e['actual'] is None else e['actual'] for e in entries)
            if total + maximum_microeur > limit:
                raise RuntimeError(f'{period}_spending_limit')
        state['entries'][request_id] = {'day':day, 'reserved':maximum_microeur,
                                        'actual':None, 'usage':None}
        self.store.save(state, sha)

    def settle(self, request_id, actual_microeur, *, usage=None):
        with self._lock:
            return self._settle(request_id, actual_microeur, usage=usage)

    def _settle(self, request_id, actual_microeur, *, usage=None):
        if type(actual_microeur) is not int or actual_microeur < 0:
            raise ValueError('Invalid actual cost')
        state, sha = self.store.load()
        state = validate_state(state)
        row = state['entries'][request_id]
        record = Usage.model_validate(usage).model_dump() if usage is not None else None
        if row['actual'] is not None:
            if row['actual'] != actual_microeur or row['usage'] != record:
                raise ValueError('Conflicting settlement')
            return
        row['actual'], row['usage'] = actual_microeur, record
        self.store.save(state, sha)
        if actual_microeur > row['reserved']:
            raise RuntimeError('reservation_exceeded_actual_charge_recorded')

    def summary(self):
        state, _ = self.store.load()
        entries = state['entries'].values()
        settled = sum(e['actual'] for e in entries if e['actual'] is not None)
        held = sum(e['reserved'] for e in entries if e['actual'] is None)
        return {'currency':'EUR', 'settled_microeur':settled, 'held_microeur':held,
                'remaining_pilot_microeur':max(0, self.lifetime_limit-settled-held),
                'requests':len(state['entries']), 'limits_microeur':state['limits_microeur']}
