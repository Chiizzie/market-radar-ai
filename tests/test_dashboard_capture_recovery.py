import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import requests

from market_radar_ai.agents.research_artifacts import EvidenceBank
from market_radar_ai.dashboard.snapshot_recovery import restore_batch

NOW = datetime(2026, 11, 18, 23, 25, tzinfo=UTC)
SECRET = 'offline-archive-tests-only' * 2


def original(bank, seq, age, *, state='unconfirmed', source='archived_exact'):
    generated = NOW - timedelta(seconds=age)
    body = json.dumps({'generated_at_dublin': generated.isoformat(),
                       'expires_at_epoch': int(generated.timestamp()) + 60, 'test_seq': seq}) + '\n'
    key = hashlib.sha256(body.encode()).hexdigest()
    record = {**json.loads(body), 'snapshot_id': key, 'client_state': state, 'body_state': source,
              'run_id': seq, 'trade_authorized': False}
    bank.put('capture_delivery', seq, record)
    bank.put('recovery_snapshot', key, body)
    return key, record


class Dashboard:
    def __init__(self, *, drop=False, store=True, unavailable=False):
        self.rows = {}
        self.writes = []
        self.reads = 0
        self.drop, self.store, self.unavailable = drop, store, unavailable

    def get(self, url, *, params, headers, **_):
        self.reads += 1
        if self.unavailable:
            raise requests.ReadTimeout()
        keys = params['id'].split(',')
        results = [self.rows.get(k, {'state': 'absent', 'snapshot_id': k}) for k in keys]
        return SimpleNamespace(status_code=200, json=lambda: {'ok': True, 'receipts': results})

    def put(self, url, *, data, headers, timeout, allow_redirects):
        key = hashlib.sha256(data).hexdigest()
        self.writes.append(key)
        assert not allow_redirects and timeout.total <= 45
        stamp = headers['X-Timestamp'].encode()
        expected = hmac.new(SECRET.encode(), stamp + b'.scanner-snapshot-archive-v1\n' + data, hashlib.sha256).hexdigest()
        assert headers['X-Signature'] == 'sha256=' + expected
        doc = json.loads(data)
        if self.store:
            self.rows[key] = {'state': 'stored', 'snapshot_id': key, 'generated_at': doc['generated_at_dublin'],
                'expires_at_epoch': doc['expires_at_epoch'], 'received_at': NOW.isoformat(), 'recovered_from_archive': True}
        if self.drop:
            raise requests.ReadTimeout()
        return SimpleNamespace(status_code=200, json=lambda: {'ok': True, 'state': 'archived', 'snapshot_id': key})


@pytest.fixture
def bank(tmp_path):
    b = EvidenceBank(tmp_path / 'evidence.sqlite')
    yield b
    b.close()


def recover(bank, dashboard, limit=12):
    return restore_batch(bank, secret=SECRET, session=dashboard, clock=lambda: NOW, limit=limit)


def test_restore_is_expired_only_bounded_verified_and_idempotent(bank):
    recent, _ = original(bank, 1, 240)
    older, _ = original(bank, 2, 400, source='reconstructed_exact')
    original(bank, 3, 70)
    original(bank, 4, 600, state='confirmed')
    original(bank, 5, 610, source='unverified')
    db = Dashboard()
    first = recover(bank, db, 1)
    assert first['state'] == 'more_pending' and first['pending'] == [older] and first['candidates'] == 2
    assert first['verified'][0]['snapshot_id'] == recent and first['verified'][0]['recovered_from_archive']
    second = recover(bank, db)
    assert second['state'] == 'complete' and second['already_stored'] == 1
    third = recover(bank, db)
    assert third['already_stored'] == 2 and third['verified'] == [] and db.writes == [recent, older]


@pytest.mark.parametrize('store,expected', [(True, 'more_pending'), (False, 'incomplete')])
def test_ambiguous_write_is_read_back_and_never_resent_in_the_same_pass(bank, store, expected):
    first, _ = original(bank, 1, 240)
    original(bank, 2, 320)
    db = Dashboard(drop=True, store=store)
    report = recover(bank, db)
    assert db.writes == [first] and report['state'] == expected
    assert len(report['verified']) == int(store)


def test_failed_authoritative_read_never_triggers_writes(bank):
    original(bank, 1, 240)
    db = Dashboard(unavailable=True)
    report = recover(bank, db)
    assert report['state'] == 'storage_unavailable' and report['unchecked'] == 1
    assert report['failures'] == [{'phase': 'initial_lookup', 'reason': 'read_timeout',
                                   'ids_requested': 1, 'elapsed_seconds': 0}]
    assert not db.writes


def test_partial_lookup_preserves_missing_and_unchecked_counts(bank):
    for i in range(17):
        original(bank, i, 300 + i)

    class CappedGateway(Dashboard):
        def get(self, url, **kwargs):
            assert len(requests.Request('GET', url, params=kwargs['params']).prepare().url) < 2048
            if self.reads:
                return SimpleNamespace(status_code=503)
            return super().get(url, **kwargs)

    db = CappedGateway()
    report = recover(bank, db)
    assert report['missing_observed'] == len(report['pending']) == 16 and report['unchecked'] == 1
    assert report['failures'][0]['http_status'] == 503 and not db.writes


def test_uncertain_write_and_failed_readback_survive_in_same_report(bank):
    key, _ = original(bank, 1, 240)

    class SlowGateway(Dashboard):
        def get(self, url, **kwargs):
            if self.writes:
                raise requests.ConnectTimeout('sensitive provider text')
            return super().get(url, **kwargs)

    db = SlowGateway(drop=True)
    report = recover(bank, db)
    assert report['state'] == 'storage_unavailable' and report['pending'] == db.writes == [key]
    assert [(f['phase'], f['reason']) for f in report['failures']] == [
        ('archive_write', 'read_timeout'), ('readback', 'connect_timeout')]
    assert 'sensitive' not in json.dumps(report)


def test_slow_batch_can_verify_and_restore_the_newest_capture_without_guessing_the_rest(bank):
    newest, _ = original(bank, 1, 240)
    original(bank, 2, 300)

    class SlowBatch(Dashboard):
        def get(self, url, **kwargs):
            if ',' in kwargs['params']['id']:
                raise requests.ReadTimeout()
            return super().get(url, **kwargs)

    db = SlowBatch()
    report = recover(bank, db)
    assert db.writes == [newest] and report['verified'][0]['snapshot_id'] == newest
    assert report['unchecked'] == 1 and report['state'] == 'storage_unavailable'
    assert report['missing_observed'] == 1 and report['pending'] == []
    again = recover(bank, db)
    assert again['already_stored'] == 1 and db.writes == [newest]


def test_unavailable_single_read_leaves_every_identity_untouched(bank):
    for i in range(4):
        original(bank, i, 240 + i)
    db = Dashboard(unavailable=True)
    report = recover(bank, db)
    assert [(x['phase'], x['ids_requested']) for x in report['failures']] == [
        ('initial_lookup', 4), ('single_lookup', 1)]
    assert report['unchecked'] == 4 and db.reads == 2 and not db.writes


def test_inconsistent_stored_metadata_is_left_unresolved(bank):
    key, rec = original(bank, 1, 240)
    db = Dashboard()
    db.rows[key] = {'state': 'stored', 'snapshot_id': key, 'generated_at': rec['generated_at_dublin'],
                    'expires_at_epoch': rec['expires_at_epoch'] + 2, 'received_at': NOW.isoformat(),
                    'recovered_from_archive': None}
    report = recover(bank, db)
    assert report['state'] == 'incomplete' and report['unverified'] == [key] and not db.writes
