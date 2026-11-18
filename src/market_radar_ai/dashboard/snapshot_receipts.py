"""Read exact dashboard receipts without changing any snapshot or trade state."""
from datetime import datetime
import hashlib
import hmac
import re

import requests
from urllib3.util import Timeout

from .snapshot_delivery import ENDPOINT


class ReceiptUnavailable(RuntimeError):
    pass


def signed_headers(secret, now, message):
    timestamp = str(int(now.timestamp()))
    signature = hmac.new(secret.encode(), timestamp.encode() + b'.' + message, hashlib.sha256).hexdigest()
    return {'X-Timestamp': timestamp, 'X-Signature': 'sha256=' + signature}


def lookup(ids, *, secret, now, session, seconds):
    if (not 1 <= len(ids) <= 32 or len(set(ids)) != len(ids) or
            any(not isinstance(key, str) or not re.fullmatch('[a-f0-9]{64}', key) for key in ids)):
        raise ValueError('invalid_snapshot_receipt_ids')
    key = ','.join(ids)
    try:
        response = session.get(ENDPOINT, params={'id': key}, allow_redirects=False,
            headers=signed_headers(secret, now, b'scanner-snapshot-receipt-v1\n' + key.encode()),
            timeout=Timeout(total=seconds, connect=min(3.0, seconds)))
        if response.status_code != 200:
            raise ReceiptUnavailable('receipt_lookup_unavailable')
        result = response.json()
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise ReceiptUnavailable('invalid_receipt_response')
        rows = result.get('receipts')
        if (not isinstance(rows, list) or len(rows) != len(ids) or
                any(not isinstance(row, dict) or row.get('snapshot_id') != key or
                    row.get('state') not in ('absent', 'stored') for key, row in zip(ids, rows))):
            raise ReceiptUnavailable('invalid_receipt_response')
        return rows
    except (requests.RequestException, TimeoutError, ValueError):
        raise ReceiptUnavailable('receipt_lookup_unavailable') from None


def stored_at(row, original):
    """Return the actual storage clock only when all original identity fields bind."""
    if (row.get('state') != 'stored' or row.get('snapshot_id') != original.get('snapshot_id')
            or type(row.get('expires_at_epoch')) is not int or row['expires_at_epoch'] != original.get('expires_at_epoch')
            or 'recovered_from_archive' not in row or
            (row['recovered_from_archive'] is not None and type(row['recovered_from_archive']) is not bool)):
        return None
    try:
        source = datetime.fromisoformat(original['generated_at_dublin'])
        generated = datetime.fromisoformat(row['generated_at'])
        received = datetime.fromisoformat(row['received_at'])
        if any(t.tzinfo is None for t in (source, generated, received)) or generated != source or received < generated:
            return None
        return received
    except (KeyError, TypeError, ValueError):
        return None
