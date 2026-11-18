import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from market_radar_ai.dashboard.snapshot_delivery import deliver, SnapshotDeliveryError
from market_radar_ai.dashboard.snapshot_receipts import lookup, ReceiptUnavailable
from test_dashboard_cache import capture
from test_market_capture import NOW
from test_snapshot_delivery import ENV, Session


class TimedOut(Session):
    def __init__(self, state='stored', status=200, fault='read_timeout'):
        super().__init__(fault)
        self.reads = 0
        self.state = state
        self.status = status

    def get(self, url, *, params, headers, timeout, allow_redirects):
        self.reads += 1
        assert not allow_redirects and 0 < timeout.total <= 8
        key = params['id']
        stamp = headers['X-Timestamp']
        sign = hmac.new(('x' * 32).encode(), (stamp + '.scanner-snapshot-receipt-v1\n' + key).encode(),
                        hashlib.sha256).hexdigest()
        assert headers['X-Signature'] == 'sha256=' + sign
        original = json.loads(self.calls[0]['data'])
        row = {'state': 'stored', 'snapshot_id': key, 'generated_at': original['generated_at_dublin'],
               'expires_at_epoch': original['expires_at_epoch'],
               'received_at': (NOW + timedelta(seconds=29)).isoformat(), 'recovered_from_archive': None}
        if self.state == 'absent':
            row = {'state': 'absent', 'snapshot_id': key}
        elif self.state == 'archived':
            row['recovered_from_archive'] = True
        elif self.state == 'changed':
            row['expires_at_epoch'] += 1
        elif self.state == 'wrong_id':
            row['snapshot_id'] = 'f' * 64
        elif self.state == 'future':
            row['received_at'] = (NOW + timedelta(seconds=90)).isoformat()
        return SimpleNamespace(status_code=self.status, json=lambda: {'ok': True, 'receipts': [row]})


def run(transport, *, start=38, finished=42):
    clocks = iter([NOW, NOW, NOW + timedelta(seconds=start), NOW + timedelta(seconds=finished)])
    return deliver(capture(), env={**ENV, 'SCANNER_VERIFY_TIMEOUT_RECEIPT': 'true'},
                   clock=lambda: next(clocks), session=transport)


@pytest.mark.parametrize('fault', ['read_timeout', 'duplicate'])
def test_lost_original_reply_can_be_confirmed_without_resending(fault):
    transport = TimedOut(fault=fault)
    result = run(transport)
    assert result['confirmation_source'] == 'stored_receipt'
    assert result['acknowledged_before_expiry'] and result['trade_authorized'] is False
    assert len(transport.calls) == transport.reads == 1


def test_read_completed_at_expiry_is_archival_only():
    transport = TimedOut()
    receipt = run(transport, finished=60)
    assert receipt['state'] == 'scanner_snapshot_delivery_confirmed' and not receipt['acknowledged_before_expiry']


@pytest.mark.parametrize('state,status', [('absent', 200), ('archived', 200), ('changed', 200),
                                         ('wrong_id', 200), ('future', 200), ('stored', 503)])
def test_unusable_receipt_never_authorizes_review(state, status):
    transport = TimedOut(state, status)
    with pytest.raises(SnapshotDeliveryError) as exc:
        run(transport)
    assert exc.value.receipt['state'] == 'scanner_snapshot_delivery_unconfirmed'
    assert exc.value.receipt['reason'] == 'read_timeout' and len(transport.calls) == transport.reads == 1


def test_no_read_or_resubmission_when_time_is_exhausted():
    transport = TimedOut()
    with pytest.raises(SnapshotDeliveryError) as exc:
        run(transport, start=59)
    assert exc.value.receipt['receipt_lookup'] == 'insufficient_time'
    assert not transport.reads and len(transport.calls) == 1


def test_bad_batch_fails_without_contacting_the_server():
    with pytest.raises(ValueError):
        lookup(['f' * 64] * 2, secret='x'*32, now=NOW, session=None, seconds=8)
    for bad in ({}, {'ok': True, 'receipts': []}, {'ok': True, 'receipts': [None]}):
        session = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: bad))
        with pytest.raises(ReceiptUnavailable):
            lookup(['a'*64], secret='x'*32, now=NOW, session=session, seconds=8)
