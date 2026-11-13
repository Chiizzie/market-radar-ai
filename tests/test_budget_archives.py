"""Financial history survives rotation, restarts, conflicts and ambiguous writes."""
import base64
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
import requests

from market_radar_ai.agents.budget_archive import ArchiveCodec, encode, git_sha
from market_radar_ai.agents.github_budget import (
    GitHubBudgetStore, GitHubSpendingLedger, initial_state, validate_state, URL,
)
from market_radar_ai.dashboard.api_budget import summarize
from test_spending import NOW


def history(count=760):
    state = initial_state()
    for i in range(count):
        state['entries'][f'paid:{i:064x}'] = {
            'day': '2026-11-01', 'reserved': 500, 'actual': 400,
            'usage': {'response_id': 'receipt-'+str(i)+'x'*90, 'model': 'offline-fixture',
                      'input_tokens': 50, 'output_tokens': 5, 'cached_input_tokens': 0,
                      'cost_usd': '0.0004', 'eur_per_usd': '1', 'pricing_checked': '2026-11-02'},
        }
    state['entries']['old-unknown'] = {'day': '2026-10-01', 'reserved': 1000, 'actual': None, 'usage': None}
    return state


class Remote:
    def __init__(self, state):
        self.raw = encode(state)
        self.files = {}
        self.puts = []
        self.gets = []
        self.root_conflict = False
        self.root_lost_ack = False
        self.archive_failure = False
        self.archive_lost_ack = False
        self.stale = None

    def response(self, raw):
        return SimpleNamespace(status_code=200, json=lambda: {
            'encoding': 'base64', 'size': len(raw), 'sha': git_sha(raw),
            'content': base64.b64encode(raw).decode(),
        })

    def get(self, url, **kw):
        self.gets.append((url, kw))
        if url == URL:
            return self.response(self.stale or self.raw)
        if '/git/blobs/' in url:
            raw = next((r for r in self.files.values() if git_sha(r) == url.rsplit('/', 1)[1]), None)
        else:
            raw = self.files.get(url)
        return self.response(raw) if raw is not None else SimpleNamespace(status_code=404, headers={})

    def put(self, url, **kw):
        self.puts.append((url, deepcopy(kw)))
        raw = base64.b64decode(kw['json']['content'])
        if url != URL:
            assert 'sha' not in kw['json']  # Never overwrite an immutable archive.
            if self.archive_failure:
                return SimpleNamespace(status_code=503, headers={})
            if url in self.files:
                return SimpleNamespace(status_code=422, headers={})
            self.files[url] = raw
            if self.archive_lost_ack:
                raise requests.Timeout('private transport details')
            return SimpleNamespace(status_code=201, json=lambda: {'content': {'sha': git_sha(raw)}})
        if self.root_conflict:
            self.root_conflict = False
            state = json.loads(self.raw)
            state['entries']['concurrent'] = {'day': NOW.date().isoformat(), 'reserved': 500000,
                                             'actual': None, 'usage': None}
            self.raw = encode(state)
        if kw['json']['sha'] != git_sha(self.raw):
            return SimpleNamespace(status_code=409)
        self.raw = raw
        if self.root_lost_ack:
            raise requests.Timeout('private transport details')
        return SimpleNamespace(status_code=200)


def wire(monkeypatch, remote, *, enabled=True):
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.get', remote.get)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.requests.put', remote.put)
    monkeypatch.setattr('market_radar_ai.agents.github_budget.time.sleep', lambda _: None)
    return GitHubSpendingLedger(GitHubBudgetStore('offline-secret', archive_writes=enabled))


def test_rotation_preserves_all_receipts_and_period_totals_on_restart(monkeypatch):
    original = history()
    assert 240000 < len(encode(original)) < 500000
    remote = Remote(original)
    ledger = wire(monkeypatch, remote)
    ledger.reserve('today', 10000, NOW)
    physical = json.loads(remote.raw)
    assert physical['version'] == 2 and len(remote.raw) < 130000 and remote.files
    assert 'old-unknown' in physical['entries'] and 'today' in physical['entries']
    expected = deepcopy(original)
    expected['entries']['today'] = {'day': NOW.date().isoformat(), 'reserved': 10000, 'actual': None, 'usage': None}
    restarted = wire(monkeypatch, remote, enabled=False)
    state, _ = restarted.store.load()
    assert state == expected
    assert summarize(state, now=NOW) == summarize(expected, now=NOW)
    with pytest.raises(ValueError):
        validate_state(physical)  # Legacy readers fail closed rather than ignore history.
    restarted.settle('today', 700)
    assert restarted.summary()['held_microeur'] == 1000
    with pytest.raises(ValueError, match='already reserved'):
        restarted.reserve(next(iter(original['entries'])), 1, NOW)


def test_logical_growth_beyond_old_file_ceiling_rotates_without_budget_reset(monkeypatch):
    original = history()
    original['entries']['earlier-lifetime-charge'] = {
        'day': '2025-01-01', 'reserved': 99000000, 'actual': 99000000, 'usage': None}
    remote = Remote(original)
    ledger = wire(monkeypatch, remote)
    ledger.reserve('first', 1, NOW)
    state, version = ledger.store.load()
    for key, row in history(760)['entries'].items():
        if row['actual'] is not None:
            state['entries']['second:'+key] = deepcopy(row)
    assert len(encode(state)) > 500000
    ledger.store.save(state, version)
    assert len(remote.raw) < 240000
    fresh = wire(monkeypatch, remote)
    loaded, _ = fresh.store.load()
    assert loaded == state and loaded['limits_microeur'] == original_limits()
    # The October reservation and November archived charges still consume the
    # December lifetime allowance even though daily/monthly views have reset.
    with pytest.raises(RuntimeError, match='lifetime_spending_limit'):
        fresh.reserve('over-lifetime', 500000, NOW.replace(month=12))


def original_limits():
    return {'daily': 1000000, 'monthly': 10000000, 'lifetime': 100000000}


def test_rotation_conflict_preserves_competing_reservation_and_rechecks_allowance(monkeypatch):
    remote = Remote(history())
    ledger = wire(monkeypatch, remote)
    remote.root_conflict = True
    with pytest.raises(RuntimeError, match='daily_spending_limit'):
        ledger.reserve('ours', 600000, NOW)
    state, _ = wire(monkeypatch, remote).store.load()
    assert 'ours' not in state['entries'] and state['entries']['concurrent']['reserved'] == 500000
    # Unused immutable files do not reduce the accounting state.
    assert remote.files and all(row['actual'] is not None for raw in remote.files.values()
                                for row in json.loads(raw)['entries'].values())


def test_archive_upload_failure_never_updates_authority_or_calls_model(monkeypatch):
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from test_openai_pilot import SCHEMA
    remote = Remote(history())
    before = remote.raw
    remote.archive_failure = True
    ledger = wire(monkeypatch, remote)
    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post',
                        lambda *a, **k: pytest.fail('No model without confirmed reservation'))
    client = OpenAIPilot(api_key='offline', ledger=ledger, eur_per_usd=1, enabled=True)
    with pytest.raises(RuntimeError):
        client.call(prompt='fixture', schema=SCHEMA, request_id='paid', now=NOW)
    assert remote.raw == before and all(url != URL for url, _ in remote.puts)


def test_lost_manifest_ack_holds_reservation_and_forbids_paid_retry(monkeypatch):
    from market_radar_ai.agents.openai_pilot import OpenAIPilot
    from test_openai_pilot import SCHEMA
    remote = Remote(history())
    remote.root_lost_ack = True
    ledger = wire(monkeypatch, remote)
    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post',
                        lambda *a, **k: pytest.fail('Unknown acceptance must not call model'))
    client = OpenAIPilot(api_key='offline', ledger=ledger, eur_per_usd=1, enabled=True)
    with pytest.raises(RuntimeError, match='acceptance_unknown'):
        client.call(prompt='fixture', schema=SCHEMA, request_id='paid', now=NOW)
    assert sum(url == URL for url, _ in remote.puts) == 1
    remote.root_lost_ack = False
    restarted = wire(monkeypatch, remote)
    with pytest.raises(ValueError, match='already reserved'):
        restarted.reserve('paid', 1, NOW)
    assert restarted.store.load()[0]['entries']['paid']['actual'] is None


def test_lost_archive_ack_is_read_confirmed_without_repeating_upload(monkeypatch):
    remote = Remote(history())
    remote.archive_lost_ack = True
    ledger = wire(monkeypatch, remote)
    ledger.reserve('paid', 1, NOW)
    assert len([u for u, _ in remote.puts if u != URL]) == len(remote.files)
    assert wire(monkeypatch, remote).store.load()[0]['entries']['paid']['reserved'] == 1


def test_archives_are_cached_but_each_manifest_cas_still_guards_current_state(monkeypatch):
    remote = Remote(history())
    ledger = wire(monkeypatch, remote)
    ledger.reserve('one', 10, NOW)
    fresh = wire(monkeypatch, remote)
    fresh.store.load()
    archive_reads = sum('/git/blobs/' in url for url, _ in remote.gets)
    fresh.store.load()
    assert sum('/git/blobs/' in url for url, _ in remote.gets) == archive_reads
    uploads = len(remote.files)
    fresh.reserve('two', 20, NOW)
    fresh.settle('two', 15)
    assert len(remote.files) == uploads


@pytest.mark.parametrize('damage', ['missing', 'mutated', 'duplicate', 'pending', 'index_hash', 'version'])
def test_damaged_or_ambiguous_archive_cannot_reduce_spending(monkeypatch, damage):
    remote = Remote(history())
    ledger = wire(monkeypatch, remote)
    ledger.reserve('paid', 1, NOW)
    manifest = json.loads(remote.raw)
    if damage == 'missing':
        remote.files.clear()
    elif damage == 'mutated':
        key = next(iter(remote.files))
        remote.files[key] += b' '
    elif damage == 'duplicate':
        manifest['archives'].append(deepcopy(manifest['archives'][0]))
    elif damage == 'pending':
        # Even a self-consistent archive digest cannot hide unresolved holds.
        from market_radar_ai.agents.budget_archive import reference
        key = next(iter(remote.files))
        part = json.loads(remote.files[key])
        next(iter(part['entries'].values()))['actual'] = None
        raw = encode(part)
        manifest['archives'][0] = reference(raw, len(part['entries']))
        remote.files[key] = raw
    elif damage == 'index_hash':
        manifest['archives'][0]['sha256'] = 'f'*64
    else:
        manifest['version'] = 99
    remote.raw = encode(manifest)
    with pytest.raises(RuntimeError, match='read failed'):
        wire(monkeypatch, remote).store.load()


def test_confirmed_history_cannot_be_deleted_or_modified_before_write(monkeypatch):
    remote = Remote(history())
    ledger = wire(monkeypatch, remote)
    ledger.reserve('paid', 1, NOW)
    state, version = ledger.store.load()
    key = next(iter(state['entries']))
    del state['entries'][key]
    before = len(remote.puts)
    with pytest.raises(ValueError, match='history'):
        ledger.store.save(state, version)
    assert len(remote.puts) == before


def test_stale_pre_rotation_read_is_rejected_after_new_reservation(monkeypatch):
    remote = Remote(history())
    original = remote.raw
    ledger = wire(monkeypatch, remote)
    ledger.reserve('paid', 1, NOW)
    ledger.store.load()  # Consume confirmed-write cache.
    remote.stale = original
    with pytest.raises(RuntimeError, match='stale_read'):
        ledger.store.load()


def test_missing_migration_opt_in_retains_legacy_format(monkeypatch):
    remote = Remote(history())
    ledger = wire(monkeypatch, remote, enabled=False)
    ledger.reserve('paid', 1, NOW)
    assert json.loads(remote.raw)['version'] == 1 and not remote.files


def test_only_pending_capacity_never_discards_holds():
    state = initial_state()
    state['entries'] = {f'pending:{i:064x}': {'day': '2026-11-01', 'reserved': 1,
        'actual': None, 'usage': None} for i in range(4000)}
    before = deepcopy(state)
    with pytest.raises(ValueError, match='pending_capacity'):
        ArchiveCodec().plan(state, enabled=True)
    assert state == before


def test_maintenance_verifies_fresh_reader_with_no_accounting_change(monkeypatch):
    from market_radar_ai.agents.budget_archive_maintenance import run
    remote = Remote(history())
    wire(monkeypatch, remote)
    report = run(token='offline', migrate=True, clock=lambda: NOW, sleep=lambda _: None)
    assert report['rotated'] and report['after']['representation'] == 'archived_v2'
    assert report['logical_before_sha256'] == report['logical_after_sha256']
    assert report['accounting']['periods']['lifetime']['reserved_microeur'] == 1000
    assert report['before']['logical_entries'] == report['after']['logical_entries']
    writes = len(remote.puts)
    again = run(token='offline', migrate=True, clock=lambda: NOW, sleep=lambda _: None)
    assert not again['rotated'] and len(remote.puts) == writes


def test_maintenance_read_only_plan_does_not_write(monkeypatch):
    from market_radar_ai.agents.budget_archive_maintenance import run
    remote = Remote(history())
    wire(monkeypatch, remote)
    report = run(token='offline', migrate=False, clock=lambda: NOW, sleep=lambda _: None)
    assert not remote.puts and report['planned_archive_files'] > 0
    assert report['after']['representation'] == 'legacy_v1'
