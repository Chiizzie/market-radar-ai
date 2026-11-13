"""Immutable settled-budget segments behind one compare-and-swap manifest.

The logical ledger remains version 1 for all spending checks. Only its storage
representation changes. Pending reservations are never archived or discarded.
"""
from copy import deepcopy
from hashlib import sha1, sha256
import json
import re

ROTATE_BYTES = 240_000
ACTIVE_TARGET_BYTES = 120_000
SEGMENT_BYTES = 120_000
MAX_ARCHIVES = 512
MANIFEST_BYTES = 500_000
ARCHIVE_DIRECTORY = 'state/ai-budget-archive'


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def git_sha(raw):
    return sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def logical(entries, currency, limits):
    from .github_budget import validate_state
    return validate_state({'version': 1, 'currency': currency,
                           'limits_microeur': limits, 'entries': entries})


def reference(raw, count):
    return {'sha256': sha256(raw).hexdigest(), 'blob_sha': git_sha(raw),
            'bytes': len(raw), 'entries': count}


def checked_references(values):
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_ARCHIVES:
        raise ValueError('budget_archive_index')
    seen = set()
    for item in values:
        if (not isinstance(item, dict) or set(item) != {'sha256', 'blob_sha', 'bytes', 'entries'}
                or not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                or not isinstance(item['blob_sha'], str) or not re.fullmatch('[0-9a-f]{40}', item['blob_sha'])
                or type(item['bytes']) is not int or not 1 <= item['bytes'] <= SEGMENT_BYTES
                or type(item['entries']) is not int or not 1 <= item['entries'] <= 2000
                or item['sha256'] in seen):
            raise ValueError('budget_archive_reference')
        seen.add(item['sha256'])
    return deepcopy(values)


class ArchiveCodec:
    def __init__(self):
        self.references = []
        self.archived = {}
        self.cache = {}

    def decode(self, document, fetch):
        if document.get('version') != 2:
            from .github_budget import validate_state
            state = validate_state(document)
            self.references, self.archived = [], {}
            return state
        if (type(document['version']) is not int
                or set(document) != {'version', 'currency', 'limits_microeur', 'entries', 'archives'}):
            raise ValueError('budget_manifest_fields')
        active = logical(document['entries'], document['currency'], document['limits_microeur'])
        refs = checked_references(document['archives'])
        entries = deepcopy(active['entries'])
        archived = {}
        for ref in refs:
            raw = self.cache.get(ref['blob_sha'])
            if raw is None:
                raw = fetch(ref)
            if (not isinstance(raw, bytes) or len(raw) != ref['bytes']
                    or sha256(raw).hexdigest() != ref['sha256'] or git_sha(raw) != ref['blob_sha']):
                raise ValueError('budget_archive_digest')
            part = json.loads(raw)
            if (set(part) != {'schema_version', 'entries'}
                    or part['schema_version'] != 'settled-budget-archive-v1'
                    or not isinstance(part['entries'], dict) or len(part['entries']) != ref['entries']):
                raise ValueError('budget_archive_shape')
            checked = logical(part['entries'], active['currency'], active['limits_microeur'])['entries']
            if any(row['actual'] is None for row in checked.values()):
                raise ValueError('budget_archive_contains_pending')
            if entries.keys() & checked.keys():
                raise ValueError('budget_archive_duplicate_identity')
            entries.update(checked)
            archived.update(checked)
            self.cache[ref['blob_sha']] = raw
        state = logical(entries, active['currency'], active['limits_microeur'])
        self.references, self.archived = refs, archived
        return state

    def plan(self, state, *, enabled):
        from .github_budget import validate_state
        state = validate_state(state)
        if not self.references and (not enabled or len(encode(state)) <= ROTATE_BYTES):
            return state, [], {}
        for key, before in self.archived.items():
            if state['entries'].get(key) != before:
                raise ValueError('budget_archived_history_changed')
        active = {key: row for key, row in state['entries'].items() if key not in self.archived}
        refs, chunks, newly_archived = deepcopy(self.references), [], {}
        # Oldest settled records rotate first. Reservations, including old or
        # ambiguous ones, remain active and still count against every allowance.
        active_size = len(encode(active))
        if active_size > ROTATE_BYTES:
            selected = {}
            for key, row in sorted(active.items(), key=lambda item: (item[1]['day'], item[0])):
                if row['actual'] is None:
                    continue
                selected[key] = row
                active_size -= len(encode({key: row})) - 1
                if active_size <= ACTIVE_TARGET_BYTES:
                    break
            batch = {}
            for key, row in selected.items():
                proposed = {**batch, key: row}
                body = {'schema_version': 'settled-budget-archive-v1', 'entries': proposed}
                if len(encode(body)) > SEGMENT_BYTES and batch:
                    raw = encode({'schema_version': 'settled-budget-archive-v1', 'entries': batch})
                    chunks.append((reference(raw, len(batch)), raw))
                    batch = {}
                batch[key] = row
                if len(encode({'schema_version': 'settled-budget-archive-v1', 'entries': batch})) > SEGMENT_BYTES:
                    raise ValueError('budget_archive_entry_capacity')
            if batch:
                raw = encode({'schema_version': 'settled-budget-archive-v1', 'entries': batch})
                chunks.append((reference(raw, len(batch)), raw))
            refs.extend(ref for ref, _ in chunks)
            newly_archived = selected
            active = {key: row for key, row in active.items() if key not in selected}
        if not refs:
            # A full file consisting only of unresolved reservations must fail
            # closed; it must never be "fixed" by deleting their held amounts.
            if len(encode(state)) > MANIFEST_BYTES:
                raise ValueError('budget_pending_capacity')
            return state, [], {}
        checked_references(refs)
        document = {**state, 'version': 2, 'entries': active, 'archives': refs}
        if len(encode(document)) > MANIFEST_BYTES:
            raise ValueError('budget_manifest_capacity')
        return document, chunks, newly_archived

    def confirm(self, document, chunks, newly_archived):
        if document['version'] == 2:
            self.references = deepcopy(document['archives'])
            self.archived.update(deepcopy(newly_archived))
            for ref, raw in chunks:
                self.cache[ref['blob_sha']] = raw
