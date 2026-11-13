"""Small compare-and-swap ledger on a dedicated branch; never silently reinitializes."""
import base64
import json
import os
import re
import time
from datetime import date
from threading import RLock
from zoneinfo import ZoneInfo
from typing import Literal
import requests
from .budget_archive import ArchiveCodec, ARCHIVE_DIRECTORY, SEGMENT_BYTES, encode, git_sha
from pydantic import BaseModel, ConfigDict, Field
from ..github_state import ConfirmedWrites, LedgerConflict, StaleLedgerRead, fresh_params

REPOSITORY = 'Chiizzie/market-radar-ai'
BRANCH = 'state/ai-budget'
PATH = 'state/ai-budget.json'
URL = f'https://api.github.com/repos/{REPOSITORY}/contents/{PATH}'
LIMITS = {'daily':1000000, 'monthly':10000000, 'lifetime':100000000}


class BudgetWriteError(RuntimeError):
    """Safe structured diagnostics; no provider body or credentials escape."""
    def __init__(self, code, reason, *, attempts=1, retry_after_seconds=None):
        self.diagnostic = {'code': code, 'reason': reason, 'attempts': attempts,
                           'retry_after_seconds': retry_after_seconds}
        super().__init__(f'Budget write unconfirmed [{code};reason={reason}]; paid calls disabled')


def write_refusal(response):
    headers = {str(k).lower(): str(v) for k, v in (getattr(response, 'headers', {}) or {}).items()}
    retry = headers.get('retry-after')
    delay = int(retry) if retry and retry.isdigit() and len(retry) < 10 else None
    primary = headers.get('x-ratelimit-remaining') == '0'
    if primary:
        reset = headers.get('x-ratelimit-reset', '')
        if reset.isdigit() and len(reset) < 12:
            remaining = max(1, int(reset) - int(time.time()) + 1)
            delay = max(delay or 0, remaining)
    # Classify only known phrases. Never log arbitrary error text or URLs.
    limited = False
    try:
        message = response.json().get('message', '')
        limited = isinstance(message, str) and ('rate limit' in message[:1000].lower())
    except (AttributeError, TypeError, ValueError):
        pass
    if primary: reason = 'primary_rate_limit'
    elif response.status_code == 429 or limited or delay is not None: reason = 'rate_limited'
    elif response.status_code == 403: reason = 'forbidden_unclassified'
    else: reason = 'http_refusal'
    return reason, delay


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
    def __init__(self, token, *, archive_writes=None):
        if not token:
            raise ValueError('GitHub token required')
        self._headers = {'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
                         'X-GitHub-Api-Version':'2022-11-28', 'Cache-Control':'no-cache'}
        self._confirmed = ConfirmedWrites()
        self._archives = ArchiveCodec()
        self._archive_writes = (os.environ.get('AI_BUDGET_ARCHIVE_WRITES') == 'true'
                                if archive_writes is None else archive_writes is True)
        self._loaded_state = None
        self._loaded_sha = None
        self._root_bytes = None

    def _loaded(self, state, sha):
        from copy import deepcopy
        self._loaded_state, self._loaded_sha = deepcopy(state), sha
        return state, sha

    def storage_summary(self):
        if self._loaded_state is None:
            raise ValueError('Budget storage must be read first')
        return {'representation': 'archived_v2' if self._archives.references else 'legacy_v1',
                'root_bytes': self._root_bytes, 'archive_files': len(self._archives.references),
                'archived_entries': len(self._archives.archived),
                'active_entries': len(self._loaded_state['entries'])-len(self._archives.archived),
                'logical_entries': len(self._loaded_state['entries'])}

    def _archive_read(self, ref, *, path=False):
        suffix = (f'contents/{ARCHIVE_DIRECTORY}/{ref["sha256"]}.json' if path
                  else 'git/blobs/'+ref['blob_sha'])
        url = f'https://api.github.com/repos/{REPOSITORY}/'+suffix
        for attempt in range(3):
            try:
                response = requests.get(url, params=fresh_params(BRANCH) if path else {},
                    headers=self._headers, timeout=(10, 30), allow_redirects=False)
                if response.status_code == 200:
                    data = response.json()
                    if (data.get('encoding') != 'base64' or data.get('sha') != ref['blob_sha']
                            or type(data.get('size')) is not int or not 1 <= data['size'] <= SEGMENT_BYTES):
                        raise ValueError('budget_archive_response')
                    raw = base64.b64decode(data['content'])
                    if len(raw) != data['size']:
                        raise ValueError('budget_archive_size')
                    return raw
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
            except requests.RequestException:
                pass
            except (ValueError, KeyError, TypeError):
                raise RuntimeError('Budget archive read failed [invalid_payload]; paid calls disabled') from None
            if attempt < 2:
                time.sleep(attempt + 1)
        raise RuntimeError('Budget archive read unavailable; paid calls disabled') from None

    def _archive_create(self, ref, raw):
        # Archive creation does not change spending authority. Only the later
        # manifest CAS does. An interrupted rotation leaves harmless unused files.
        url = f'https://api.github.com/repos/{REPOSITORY}/contents/{ARCHIVE_DIRECTORY}/{ref["sha256"]}.json'
        payload = {'branch': BRANCH, 'message': 'Preserve immutable settled AI budget history',
                   'content': base64.b64encode(raw).decode()}
        try:
            response = requests.put(url, headers=self._headers, timeout=(10, 30),
                                    allow_redirects=False, json=payload)
        except requests.RequestException:
            # Read-only confirmation of immutable content is safe; do not repeat
            # an ambiguous write, and never infer a financial reservation here.
            if self._archive_read(ref, path=True) == raw:
                return
            raise BudgetWriteError('transport', 'archive_acceptance_unknown') from None
        if response.status_code == 201:
            try:
                if response.json()['content']['sha'] == ref['blob_sha']:
                    return
            except (KeyError, TypeError, ValueError):
                pass
            raise BudgetWriteError('archive_response', 'archive_acceptance_unknown')
        if response.status_code == 422 and self._archive_read(ref, path=True) == raw:
            # A concurrent rotation may have created the exact same file. Never
            # overwrite it or reuse a path whose bytes do not match its digest.
            return
        reason, delay = write_refusal(response)
        raise BudgetWriteError(f'http_{int(response.status_code)}', reason,
                               retry_after_seconds=delay)

    def load(self):
        cached = self._confirmed.take()
        if cached is not None:
            return self._loaded(*cached)
        # Only idempotent reads retry here. A confirmed write can be read directly
        # without racing GitHub's branch-content cache; its SHA still guards CAS.
        reason = 'transport_unavailable'
        for attempt in range(3):
            response = None
            delay = attempt + 1
            try:
                response = requests.get(URL, params=fresh_params(BRANCH), headers=self._headers,
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
                        raw = base64.b64decode(data['content'])
                        if len(raw) > 500000:
                            raise ValueError('Invalid budget file')
                        document = json.loads(raw)
                        sha = data['sha']
                        if not re.fullmatch(r'[0-9a-f]{40}', sha):
                            raise ValueError('Invalid budget version')
                        state = self._archives.decode(document, self._archive_read)
                        self._confirmed.accept(state)
                        self._root_bytes = len(raw)
                        return self._loaded(state, sha)
                    except StaleLedgerRead:
                        reason = 'stale_read'
                        if attempt < 2:
                            time.sleep(attempt + 1)
                            continue
                        break
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
        if self._loaded_sha == expected_sha and self._loaded_state is not None:
            for key, before in self._loaded_state['entries'].items():
                after = state['entries'].get(key)
                if (after is None or before['day'] != after['day'] or before['reserved'] != after['reserved']
                        or before['actual'] is not None and before != after):
                    raise ValueError('Budget history cannot be removed or changed')
        document, chunks, newly_archived = self._archives.plan(state, enabled=self._archive_writes)
        if chunks and self._loaded_sha != expected_sha:
            raise ValueError('Budget rotation requires a confirmed versioned read')
        raw = encode(document)
        if len(raw) > 500000:
            raise RuntimeError('Budget record needs maintenance; paid calls disabled')
        for ref, chunk in chunks:
            self._archive_create(ref, chunk)
        payload = {'branch': BRANCH, 'sha': expected_sha,
                   'message': 'Record AI budget reservation or settlement',
                   'content': base64.b64encode(raw).decode()}
        for attempt in range(1, 4):
            try:
                response = requests.put(URL, headers=self._headers, timeout=(10,30),
                                        allow_redirects=False, json=payload)
            except requests.RequestException:
                # A lost acknowledgement is ambiguous. Never repeat this write.
                raise BudgetWriteError('transport', 'acceptance_unknown', attempts=attempt) from None
            if response.status_code == 200:
                self._archives.confirm(document, chunks, newly_archived)
                self._confirmed.remember(state, raw)
                self._root_bytes = len(raw)
                self._loaded(state, git_sha(raw))
                return
            if response.status_code == 409:
                raise LedgerConflict('Budget write conflict [http_409]; paid calls disabled')
            reason, delay = write_refusal(response)
            # Retry only an explicit, rejected throttle with a short server wait.
            # Keep the identical CAS SHA; never retry transport/5xx ambiguity.
            if (response.status_code in (403, 429) and reason in ('rate_limited', 'primary_rate_limit')
                    and delay is not None and 0 <= delay <= 5 and attempt < 3):
                time.sleep(max(1, delay))
                continue
            raise BudgetWriteError(f'http_{int(response.status_code)}', reason,
                                   attempts=attempt, retry_after_seconds=delay)


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
            for attempt in range(3):
                try:
                    return self._reserve(request_id, maximum_microeur, now)
                except LedgerConflict:
                    if attempt == 2: raise
                    time.sleep(.2 * (attempt + 1))

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

    def claim_markers(self, request_ids, now):
        """Atomically claim zero-cost cooldown/attempt markers in one CAS write."""
        if (not request_ids or len(set(request_ids)) != len(request_ids)
                or now.tzinfo is None or now.utcoffset() is None
                or any(not re.fullmatch(r'[a-zA-Z0-9:_-]{1,160}', key) for key in request_ids)):
            raise ValueError('Invalid marker identity')
        with self._lock:
            for attempt in range(3):
                state, sha = self.store.load()
                state = validate_state(state)
                if any(key in state['entries'] for key in request_ids):
                    raise ValueError('Request ID already reserved; inspect before retry')
                day = now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
                for key in request_ids:
                    state['entries'][key] = {'day': day, 'reserved': 1, 'actual': 0, 'usage': None}
                try:
                    self.store.save(state, sha)
                    return
                except LedgerConflict:
                    if attempt == 2: raise
                    time.sleep(.2 * (attempt + 1))

    def settle(self, request_id, actual_microeur, *, usage=None):
        with self._lock:
            for attempt in range(3):
                try:
                    return self._settle(request_id, actual_microeur, usage=usage)
                except LedgerConflict:
                    if attempt == 2: raise
                    time.sleep(.2 * (attempt + 1))
                except RuntimeError:
                    # Settlement is after a charged response. Read-only recovery
                    # may confirm its exact receipt, never repeat a model request.
                    try:
                        state, _ = self.store.load()
                        row = validate_state(state)['entries'].get(request_id)
                        record = Usage.model_validate(usage).model_dump() if usage is not None else None
                        if row and row['actual'] == actual_microeur and row['usage'] == record and actual_microeur <= row['reserved']:
                            return
                    except (RuntimeError, ValueError, KeyError):
                        pass
                    raise

    def _settle(self, request_id, actual_microeur, *, usage=None):
        if type(actual_microeur) is not int or actual_microeur < 0:
            raise ValueError('Invalid actual cost')
        state, sha = self.store.load()
        state = validate_state(state)
        row = state['entries'].get(request_id)
        if row is None:
            raise RuntimeError('Budget settlement reservation unavailable; hold retained')
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
