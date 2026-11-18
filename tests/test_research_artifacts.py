from copy import deepcopy
from datetime import UTC, datetime, timedelta
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.research_artifacts import (CAPTURE_FILES, EvidenceBank, GitHubReader,
    capture_snapshot, collect, restore_previous_bank, retain_delivery, zip_members)
from market_radar_ai.dashboard.snapshot_delivery import snapshot_bytes


def zipped(files):
    raw = BytesIO()
    with ZipFile(raw, 'w') as z:
        for name, value in files.items():
            z.writestr(name, value)
    return raw.getvalue()


def capture():
    docs = {
        'discovery-selection.json': {'schema_version': 'stock-selection-trace-v1', 'trade_authorized': False, 'observed_at': '2026-11-18T15:00:00Z',
            'symbols': [{'symbol': s, 'selection_reason': 'outside_technical_budget', 'technical_status': 'not_checked'}
                        for s in ('A', 'B')]},
        'qualification.json': {'schema_version': 'free-qualification-v1', 'trade_authorized': False, 'evaluated_at': '2026-11-18T15:00:01Z',
            'candidates': [{'candidate_id': 'stocks:C', 'paper_blockers': ['stale_quote'],
                            'eligible_for_paper_review': False}]},
        'paper-review-packets.json': {'trade_authorized': False, 'packets': []},
        'run-diagnostics.json': {'discovery': {'coverage': {'technical_checked': 1}}},
    }
    return {k: json.dumps(v).encode() for k, v in docs.items()}


RUN = {'id': 10, 'head_sha': 'a' * 40, 'conclusion': 'success', 'run_attempt': 1,
       'created_at': '2026-11-18T15:00:00Z', 'name': 'Scheduled research collection', 'status': 'completed'}
ARTIFACT = {'id': 11, 'created_at': '2026-11-18T15:05:00Z', 'digest': None,
            'name': 'scheduled-capture-10', 'expired': False}


def test_candidate_funnel_keeps_deferrals_distinct_from_rejections_and_missing():
    files = capture(); s = capture_snapshot(files, run=RUN, artifact=ARTIFACT)
    assert s['discovery_observations'] == 2 and s['qualified_observations'] == 1
    assert s['discovery_groups'][0]['symbols'] == ['A', 'B']
    assert s['discovery_groups'][0]['state']['technical_status'] == 'not_checked'
    assert s['qualified_candidates'][0]['paper_blockers'] == ['stale_quote']
    assert s['missing_files'] == [] and s['packet_links'] == []
    del files['qualification.json']
    assert capture_snapshot(files, run=RUN, artifact=ARTIFACT)['missing_files'] == ['qualification.json']


def test_duplicate_candidate_and_packet_hash_corruption_are_rejected():
    files = capture(); d = json.loads(files['discovery-selection.json'])
    d['symbols'].append(d['symbols'][0]); files['discovery-selection.json'] = json.dumps(d).encode()
    with pytest.raises(ValueError, match='duplicate_discovery_symbol'):
        capture_snapshot(files, run=RUN, artifact=ARTIFACT)
    files = capture(); files['paper-review-packets.json'] = json.dumps({'trade_authorized': False,
        'packets': [{'packet': {}, 'packet_id': 'bad'}]}).encode()
    with pytest.raises(ValueError, match='candidate_packet_hash'):
        capture_snapshot(files, run=RUN, artifact=ARTIFACT)


def test_bank_is_additive_idempotent_and_checks_read_integrity(tmp_path):
    bank = EvidenceBank(tmp_path / 'bank.sqlite')
    snapshot = capture_snapshot(capture(), run=RUN, artifact=ARTIFACT)
    assert bank.put('capture', 11, snapshot) is True
    assert bank.put('capture', 11, snapshot) is False
    bad = deepcopy(snapshot); bad['qualified_observations'] = 100
    with pytest.raises(ValueError, match='immutable_evidence_conflict'):
        bank.put('capture', 11, bad)
    assert list(bank.rows('capture')) == [snapshot]
    bank.put('run', '99:1', {'id': 99, 'attempt': 1, 'conclusion': 'failure'})
    assert bank.summary()['missing_capture_run_ids'] == [99]
    bank.db.execute("UPDATE records SET sha='bad' WHERE kind='capture'"); bank.db.commit()
    with pytest.raises(ValueError, match='evidence_bank_corruption'):
        list(bank.rows('capture'))
    bank.close()


def test_zip_reader_never_extracts_paths_and_refuses_ambiguous_files():
    assert zip_members(zipped({'dir/report.json': '{}', 'ignored.sh': 'do not run'}), {'report.json'}) == {'report.json': b'{}'}
    with pytest.raises(ValueError, match='unsafe_artifact_path'):
        zip_members(zipped({'../report.json': '{}'}), {'report.json'})
    with pytest.raises(ValueError, match='ambiguous'):
        zip_members(zipped({'one/report.json': '{}', 'two/report.json': '{}'}), {'report.json'})


def test_reader_uses_only_get_expected_repository_and_actions_endpoints():
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {'workflow_runs': []}, close=lambda: None)
    reader = GitHubReader('test-not-real', session=SimpleNamespace(get=get))
    assert reader.runs('2026-11-18') == []
    assert calls[0][0] == 'https://api.github.com/repos/Chiizzie/market-radar-ai/actions/runs'
    assert calls[0][1]['params']['created'] == '2026-11-18'
    for path in ('/issues', '/actions/runs', '/runs/../secrets', '/artifacts/1'):
        with pytest.raises(ValueError, match='read_only'):
            reader.get(path)


def test_reader_redacts_failures_and_rejects_archive_digest_mismatch():
    response = SimpleNamespace(status_code=403, close=lambda: None)
    reader = GitHubReader('secret-should-not-escape', session=SimpleNamespace(get=lambda *a, **k: response))
    with pytest.raises(RuntimeError, match='http_403') as e:
        reader.get('/runs')
    assert 'secret' not in str(e.value)
    reader.get = lambda *a, **k: b'altered'
    with pytest.raises(ValueError, match='digest_mismatch'):
        reader.download({'id': 1, 'expired': False, 'digest': 'sha256:' + '0' * 64})


def test_partial_failure_bank_is_restored_and_expired_history_never_resets(tmp_path):
    old = EvidenceBank(tmp_path / 'old.sqlite'); old.put('run', 1, {'id': 1}); old.close()
    raw = zipped({'evidence-bank.sqlite.gz': gzip.compress((tmp_path / 'old.sqlite').read_bytes())})
    run = {**RUN, 'name': 'Paper performance intelligence', 'conclusion': 'failure'}
    artifact = {**ARTIFACT, 'name': 'performance-evidence-bank-10-1'}
    reader = SimpleNamespace(artifacts=lambda r: [artifact], download=lambda a: raw)
    assert restore_previous_bank(reader, [run], tmp_path / 'recovered.sqlite') == 10
    restored = EvidenceBank(tmp_path / 'recovered.sqlite')
    assert list(restored.rows('run')) == [{'id': 1}]; restored.close()
    artifact['expired'] = True
    with pytest.raises(ValueError, match='do_not_silently_reset'):
        restore_previous_bank(reader, [run], tmp_path / 'new.sqlite')


def test_intake_skips_empty_success_and_records_failed_capture_gap(tmp_path):
    execution = {**RUN, 'id': 20, 'name': 'Execution research and readiness'}
    empty = {**execution, 'id': 21, 'created_at': '2026-11-18T16:00:00Z'}
    failed = {**RUN, 'id': 12, 'conclusion': 'failure'}
    artifact = {**ARTIFACT, 'id': 22, 'name': 'execution-research-20'}
    reader = SimpleNamespace(artifacts=lambda r: [artifact] if r['id'] == 20 else [],
        download=lambda a: zipped({'report.json': '{}', 'source-events.jsonl.gz': gzip.compress(b'')}))
    bank = EvidenceBank(tmp_path / 'bank.sqlite')
    sources = collect(reader, [empty, execution, failed], bank, tmp_path / 'output')
    assert sources['execution']['run_id'] == 20
    assert bank.summary()['missing_capture_run_ids'] == [12]
    bank.close()


def test_workflow_has_no_trading_provider_notification_or_model_secrets():
    text = Path('.github/workflows/performance-intelligence.yml').read_text()
    assert 'secrets.' not in text and 'contents: write' not in text
    assert 'GH_TOKEN: ${{ github.token }}' in text
    assert 'cancel-in-progress: false' in text
    assert '--publish' not in text


def test_bounded_backfill_resumes_without_erasing_or_redownloading_history(tmp_path):
    execution = {**RUN, 'id': 20, 'name': 'Execution research and readiness'}
    source = {**ARTIFACT, 'id': 22, 'name': 'execution-research-20'}
    calls = []
    def download(a):
        calls.append(a['id'])
        return zipped(capture()) if a['id'] == ARTIFACT['id'] else zipped({
            'report.json': '{}', 'source-events.jsonl.gz': gzip.compress(b'')})
    reader = SimpleNamespace(artifacts=lambda r: [source] if r['id'] == 20 else [ARTIFACT], download=download)
    bank = EvidenceBank(tmp_path / 'bank.sqlite')
    collect(reader, [execution, RUN], bank, tmp_path / 'first', maximum_new_artifacts=0)
    first = json.loads((tmp_path / 'first/intake.json').read_text())
    assert first['state'] == 'backfill_pending' and first['pending_artifact_ids'] == [11]
    collect(reader, [execution, RUN], bank, tmp_path / 'second')
    collect(reader, [execution, RUN], bank, tmp_path / 'third')
    assert calls.count(11) == 1 and bank.summary()['capture_snapshots'] == 1
    assert bank.summary()['missing_capture_run_ids'] == []
    bank.close()


@pytest.mark.parametrize('deadline,expected', [(None, 1), (0, 1), (float('inf'), 8)])
def test_expiry_priority_bounded_after_close_and_resume(tmp_path, deadline, expected):
    now = datetime.now(UTC)
    runs = [{**RUN, 'id': n, 'created_at': (now + timedelta(seconds=n-20)).isoformat()}
            for n in range(1, 11)]
    artifacts = {r['id']: {**ARTIFACT, 'id': r['id'], 'name': f"scheduled-capture-{r['id']}",
                     'expires_at': (now + timedelta(hours=r['id'])).isoformat()} for r in runs}
    seen = []
    def download(a):
        seen.append(a['id'])
        return zipped(capture())
    reader = SimpleNamespace(artifacts=lambda r: [artifacts[r['id']]], download=download)
    bank = EvidenceBank(tmp_path/'bank.sqlite')
    with pytest.raises(ValueError, match='no_completed_execution_evidence'):
        collect(reader, runs, bank, tmp_path, maximum_new_artifacts=1, catch_up_deadline=deadline)
    assert seen == list(range(1, expected+1))
    summary = json.loads((tmp_path/'intake.json').read_text())
    assert summary['pending_within_36_hours'] == 10-expected
    assert summary['next_pending_expiry'] == artifacts[expected+1]['expires_at']
    with pytest.raises(ValueError, match='no_completed_execution_evidence'):
        collect(reader, runs, bank, tmp_path)
    assert seen == list(range(1, 11)) and bank.summary()['capture_snapshots'] == 10
    bank.close()


def test_failed_intake_never_marks_unvisited_dates_complete(tmp_path, monkeypatch):
    from market_radar_ai.agents import research_artifacts as module
    reader = SimpleNamespace(previous_runs=lambda: [], runs=lambda day: [RUN])
    monkeypatch.setattr(module, 'GitHubReader', lambda token: reader)
    def failing(*args, **kwargs):
        raise RuntimeError('simulated_mid_intake_failure')
    monkeypatch.setattr(module, 'collect', failing)
    output = tmp_path / 'intake'
    monkeypatch.setattr('sys.argv', ['intake', '--day', '2026-11-18', '--output', str(output)])
    with pytest.raises(RuntimeError, match='simulated_mid_intake_failure'):
        module.main()
    bank = EvidenceBank(output / 'evidence-bank.sqlite')
    assert list(bank.rows('day_inventory')) == []
    assert (output / 'evidence-bank.sqlite.gz').is_file()
    bank.close()


def test_optional_opening_evidence_survives_intake_without_reclassifying_older_captures():
    files=capture()
    old=capture_snapshot(files,run=RUN,artifact=ARTIFACT)
    assert 'opening_session' not in old and old['missing_files'] == []
    brief={'schema_version':'opening-session-brief-v1','trade_authorized':False,'window':'opening_range','state':'observed'}
    files['opening-session.json']=json.dumps(brief).encode()
    new=capture_snapshot(files,run=RUN,artifact=ARTIFACT)
    assert new['opening_session'] == brief and new['missing_files'] == []
    files['opening-session.json']=json.dumps({**brief,'trade_authorized':True}).encode()
    with pytest.raises(ValueError,match='opening_capture_scope'):
        capture_snapshot(files,run=RUN,artifact=ARTIFACT)


def recovery_inputs():
    clock = {'generated_at_dublin': '2026-11-18T20:01:10+00:00',
             'expires_at_epoch': 1795032130, 'coverage': {}}
    snapshot = {'schema_version': '1.0', 'mode': 'RESEARCH_ONLY', 'live_orders_enabled': False, **clock}
    wire = snapshot_bytes(snapshot)
    receipt = {'state': 'scanner_snapshot_delivery_unconfirmed', 'trade_authorized': False,
               'snapshot_id': hashlib.sha256(wire).hexdigest(), **clock}
    packet = {'candidate_id': 'stocks:TEST', 'assembled_at': clock['generated_at_dublin'], 'live_trade_authorized': False}
    files = capture() | {'dashboard.json': wire, 'delivery.json': json.dumps(receipt).encode(),
        'paper-review-packets.json': json.dumps({'trade_authorized': False,
            'packets': [{'packet_id': digest(packet), 'packet': packet}]}).encode()}
    return files, snapshot, receipt, packet


def test_recovery_is_exact_additive_and_survives_missing_portfolio_source(tmp_path):
    files, _, receipt, packet = recovery_inputs()
    raw = zipped(files)
    run = {**RUN, 'conclusion': 'failure'}
    bank = EvidenceBank(tmp_path/'bank.sqlite')
    old = capture_snapshot({k: files[k] for k in CAPTURE_FILES}, run=run, artifact=ARTIFACT)
    bank.put('capture', ARTIFACT['id'], old)
    downloads = []
    def download(artifact):
        downloads.append(artifact['id'])
        return raw
    reader = SimpleNamespace(artifacts=lambda r: [ARTIFACT], download=download)
    for _ in range(2):
        with pytest.raises(ValueError, match='no_completed_execution_evidence'):
            collect(reader, [run], bank, tmp_path/'intake')
    meta = bank.get('capture_delivery', ARTIFACT['id'])
    assert downloads == [ARTIFACT['id']] and bank.get('capture', ARTIFACT['id']) == old
    assert meta['client_state'] == 'unconfirmed' and meta['body_state'] == 'archived_exact'
    assert bank.get('recovery_snapshot', receipt['snapshot_id']).encode() == files['dashboard.json']
    assert meta['packet_ids'] == [digest(packet)] and bank.get('recovery_packet', digest(packet)) == packet
    summary = json.loads((tmp_path/'intake/intake.json').read_text())
    assert summary['performance_source_status'] == 'execution_source_missing'
    assert summary['delivery_recovery']['unique_packets_preserved'] == 1
    assert not (tmp_path/'intake/execution/report.json').exists()
    bank.close()


@pytest.mark.parametrize('match', [True, False])
def test_legacy_reconstruction_requires_original_clock_and_exact_hash(tmp_path, monkeypatch, match):
    files, snapshot, receipt, _ = recovery_inputs()
    files['dashboard.json'] = json.dumps({**snapshot, 'generated_at_dublin': '2026-11-18T20:01:09+00:00'}).encode()
    files.update({'enriched-capture.json': b'{"capture":1}', 'news.json': b'{"news":2}'})
    def rebuild(capture, *, now, evidence):
        assert now.isoformat() == receipt['generated_at_dublin']
        assert capture == {'capture': 1} and evidence == {'news': 2}
        return snapshot if match else {**snapshot, 'different': True}
    monkeypatch.setattr('market_radar_ai.dashboard.export.build_snapshot', rebuild)
    bank = EvidenceBank(tmp_path/'bank.sqlite')
    retain_delivery(bank, zipped(files), files, run=RUN, artifact=ARTIFACT)
    meta = bank.get('capture_delivery', ARTIFACT['id'])
    assert meta['body_state'] == ('reconstructed_exact' if match else 'unverified')
    assert bank.has('recovery_snapshot', receipt['snapshot_id']) is match
    assert ('local_export_sha256' in meta) is (not match)
    bank.close()


def test_malformed_legacy_capture_falls_back_to_its_original_display_export(tmp_path):
    files, _, receipt, packet = recovery_inputs()
    files['dashboard.json'] += b'\n'
    files.update({'enriched-capture.json': b'[]', 'news.json': b'{}'})
    bank = EvidenceBank(tmp_path/'bank.sqlite')
    retain_delivery(bank, zipped(files), files, run=RUN, artifact=ARTIFACT)
    meta = bank.get('capture_delivery', ARTIFACT['id'])
    assert meta['client_state'] == 'unconfirmed' and meta['body_state'] == 'unverified'
    assert not bank.has('recovery_snapshot', receipt['snapshot_id'])
    assert bank.get('recovery_export', meta['local_export_sha256']).encode() == files['dashboard.json']
    assert meta['packet_ids'] == [digest(packet)]
    bank.close()


@pytest.mark.parametrize('receipt,state', [(None,'receipt_missing'), (b'not JSON','invalid_receipt'),
                                          (b'{"state":"unexpected"}','invalid_receipt')])
def test_missing_or_bad_receipt_retains_only_local_export_and_packet_evidence(tmp_path, receipt, state):
    files, _, _, packet = recovery_inputs()
    if receipt is None:
        files.pop('delivery.json')
    else:
        files['delivery.json'] = receipt
    bank = EvidenceBank(tmp_path/'bank.sqlite')
    retain_delivery(bank, zipped(files), files, run=RUN, artifact=ARTIFACT)
    meta = bank.get('capture_delivery', ARTIFACT['id'])
    assert meta['client_state'] == state and meta['body_state'] == 'unavailable'
    assert meta['packet_ids'] == [digest(packet)] and 'snapshot_id' not in meta
    assert bank.get('recovery_export', meta['local_export_sha256']).encode() == files['dashboard.json']
    assert list(bank.rows('recovery_snapshot')) == []
    bank.close()


def test_confirmed_delivery_has_no_outage_body_or_packet_and_wrong_scope_never_archives(tmp_path):
    files, _, receipt, packet = recovery_inputs()
    bank = EvidenceBank(tmp_path/'bank.sqlite')
    confirmed = {**receipt, 'state': 'scanner_snapshot_delivery_confirmed'}
    files['delivery.json'] = json.dumps(confirmed).encode()
    retain_delivery(bank, zipped(files), files, run=RUN, artifact=ARTIFACT)
    assert bank.get('capture_delivery', ARTIFACT['id'])['client_state'] == 'confirmed'
    assert not bank.has('recovery_packet', digest(packet)) and list(bank.rows('recovery_snapshot')) == []
    files.pop('delivery.json')
    files['dashboard.json'] = b'{"schema_version":"1.0","mode":"RESEARCH_ONLY","live_orders_enabled":true}'
    retain_delivery(bank, zipped(files), files, run=RUN, artifact={**ARTIFACT, 'id': 12})
    assert 'local_export_sha256' not in bank.get('capture_delivery', 12)
    bank.close()
