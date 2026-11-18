import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from market_radar_ai.dashboard import scanner_operations as ops


DISPATCH = datetime(2026, 11, 18, 22, 35, 10, tzinfo=UTC)
NOW = DISPATCH + timedelta(minutes=6)


def outage_sample(directory):
    parent = {'run_id': 42, 'created_at': DISPATCH.isoformat(), 'conclusion': 'failure'}
    previous = {'run_id': 41, 'created_at': (DISPATCH - timedelta(minutes=5)).isoformat(),
                'conclusion': 'failure'}
    report = {'jobs_complete': True, 'jobs_run_id': 42, 'runs': [parent, previous],
              'jobs': [{'name': 'collect', 'conclusion': 'failure'}]}
    body = b'{"historical":true}'
    (directory / 'dashboard.json').write_bytes(body)
    receipt = {'state': 'scanner_snapshot_delivery_unconfirmed', 'reason': 'read_timeout',
               'trade_authorized': False, 'snapshot_id': hashlib.sha256(body).hexdigest(),
               'generated_at_dublin': (DISPATCH + timedelta(seconds=30)).isoformat()}
    (directory / 'delivery.json').write_text(json.dumps(receipt))
    return report, receipt


def test_verified_outage_archives_report_and_signals_deferred_publication(tmp_path, monkeypatch):
    report, receipt = outage_sample(tmp_path)
    monkeypatch.setattr(ops, 'GitHubRead', Mock())
    monkeypatch.setattr(ops, 'health', Mock(return_value=report))
    monkeypatch.setattr(ops, 'datetime', type('Clock', (datetime,), {'now': staticmethod(lambda zone: NOW)}))
    client = Mock()
    monkeypatch.setattr(ops, 'EventClient', client)
    monkeypatch.setenv('HEALTH_TIMEOUT_RUN_ID', '42')
    monkeypatch.setenv('HEALTH_CAPTURE_DIR', str(tmp_path))
    output = tmp_path / 'stored' / 'report.json'
    monkeypatch.setattr(sys, 'argv', ['health', '--output', str(output)])
    with pytest.raises(SystemExit, match='publication deferred'):
        ops.main()
    client.assert_not_called()
    assert json.loads(output.read_text()) == report
    publication = json.loads((output.parent / 'publication.json').read_text())
    assert publication['snapshot_id'] == receipt['snapshot_id'] and publication['run_id'] == 42


@pytest.mark.parametrize('case', ['independent', 'wrong_parent', 'incomplete', 'other_failed_job',
                                  'quarter_first', 'previous_quarter', 'late_monitor', 'wrong_hash',
                                  'recovered', 'other_error', 'future_receipt', 'absent', 'oversized'])
def test_uncertain_evidence_and_recovery_slots_keep_ordinary_publication(tmp_path, case):
    report, receipt = outage_sample(tmp_path)
    run_id, now = '42', NOW
    if case == 'independent':
        run_id = ''
    elif case == 'wrong_parent':
        run_id = '91'
    elif case == 'incomplete':
        report['jobs_complete'] = False
    elif case == 'other_failed_job':
        report['jobs'][0]['conclusion'] = 'success'
    elif case == 'quarter_first':
        report['runs'].pop()
    elif case == 'previous_quarter':
        report['runs'][1]['created_at'] = (DISPATCH - timedelta(minutes=8)).isoformat()
    elif case == 'late_monitor':
        now = DISPATCH + timedelta(minutes=20)
    elif case == 'wrong_hash':
        (tmp_path / 'dashboard.json').write_bytes(b'changed')
    elif case == 'recovered':
        receipt['state'] = 'scanner_snapshot_delivery_confirmed'
    elif case == 'other_error':
        receipt['reason'] = 'invalid_json'
    elif case == 'future_receipt':
        receipt['generated_at_dublin'] = (now + timedelta(minutes=1)).isoformat()
    receipt_path = tmp_path / 'delivery.json'
    receipt_path.write_text(json.dumps(receipt))
    if case == 'absent':
        receipt_path.unlink()
    elif case == 'oversized':
        receipt_path.write_text(json.dumps(receipt) + ' ' * 8200)
    assert ops.deferred_health_publication(report, run_id, tmp_path, now) is None
