"""Persist bounded catalogue discovery identities, never account buy permission."""
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

SOURCE = 'trading212_metadata'
SCHEMA = 'stock-discovery-universe-v1'
REFRESH_SECONDS = 24 * 60 * 60
MAX_AGE_SECONDS = 72 * 60 * 60
MAX_SYMBOLS = 20_000
MAX_ROWS = 100_000
MAX_CACHE_BYTES = 1_000_000
SYMBOL = re.compile(r'[A-Z][A-Z0-9.\-]{0,14}')
TICKER = re.compile(r'([A-Z][A-Z0-9.\-]{0,14})_US_EQ')


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def _read_cache(path, now):
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_CACHE_BYTES + 1)
        if len(raw) > MAX_CACHE_BYTES:
            return None, 'universe_cache_oversize'
        record = json.loads(raw)
        if not isinstance(record, dict) or set(record) != {'payload', 'sha256'}:
            raise ValueError()
        payload = record['payload']
        if (not isinstance(payload, dict)
                or set(payload) != {'schema_version', 'source', 'retrieved_at', 'symbols'}
                or record['sha256'] != _digest(payload)
                or payload['schema_version'] != SCHEMA or payload['source'] != SOURCE):
            raise ValueError()
        symbols = payload['symbols']
        if (not isinstance(symbols, list) or not 1 <= len(symbols) <= MAX_SYMBOLS
                or any(not isinstance(s, str) or not SYMBOL.fullmatch(s) for s in symbols)
                or symbols != sorted(set(symbols))):
            raise ValueError()
        retrieved = datetime.fromisoformat(payload['retrieved_at'])
        if retrieved.tzinfo is None or retrieved.utcoffset() is None:
            raise ValueError()
        age = (now - retrieved).total_seconds()
        if age < 0:
            raise ValueError()
        if age > MAX_AGE_SECONDS:
            return None, 'universe_cache_expired'
        return (payload, age), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError,
            RecursionError):
        return None, 'universe_cache_invalid'


def _normalise(rows):
    symbols = set()
    for index, row in enumerate(rows):
        if index >= MAX_ROWS:
            raise ValueError('catalogue_row_limit')
        value = row.get if isinstance(row, Mapping) else lambda key, row=row: getattr(row, key, None)
        ticker = value('ticker')
        match = TICKER.fullmatch(ticker) if isinstance(ticker, str) else None
        if match and value('type') == 'STOCK' and value('currencyCode') == 'USD':
            symbols.add(match.group(1))
            if len(symbols) > MAX_SYMBOLS:
                raise ValueError('catalogue_symbol_limit')
    if not symbols:
        raise ValueError('empty_catalogue_universe')
    return sorted(symbols)


def _write_cache(path, payload):
    """Replace a complete validated cache atomically; never persist provider rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                prefix='.discovery-universe-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'payload': payload, 'sha256': _digest(payload)}, stream,
                      sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def load_universe(*, now, cache_path=None, fetch=None):
    """Reuse for 24h; failed refresh may retain metadata through 72h, never redate it.

    ``fetch`` takes no arguments and returns Trading212 catalogue rows. Cache
    persistence is optional; no path means each call fetches a new catalogue.
    ``freshness='stale_but_valid'`` explicitly identifies grace-period reuse.
    All returned symbols are research leads, not verified account eligibility.
    """
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    path = Path(cache_path) if cache_path is not None else None
    failures = []
    cached = None
    if path is not None:
        cached, failure = _read_cache(path, now)
        if failure:
            failures.append(failure)

    def result(payload, cache_status, freshness):
        return {'symbols': list(payload['symbols']) if payload else [], 'source': SOURCE,
                'retrieved_at': payload['retrieved_at'] if payload else None,
                'cache_status': cache_status, 'freshness': freshness, 'failures': failures,
                'account_permission_verified': False, 'trade_authorized': False}

    if cached and cached[1] < REFRESH_SECONDS:
        return result(cached[0], 'reused', 'fresh')
    try:
        if fetch is None:
            from .providers.catalogues import Trading212Catalogue
            fetch = Trading212Catalogue().fetch
        payload = {'schema_version': SCHEMA, 'source': SOURCE,
                   'retrieved_at': now.isoformat(), 'symbols': _normalise(fetch())}
    except Exception:  # noqa: BLE001 - provider errors must not leak credentials
        # Provider exceptions can include credentials or response bodies.
        failures.append('universe_refresh_failed')
        if cached:
            return result(cached[0], 'reused', 'stale_but_valid')
        return result(None, 'unavailable', 'unavailable')
    if path is not None:
        try:
            _write_cache(path, payload)
        except (OSError, ValueError, TypeError):
            failures.append('universe_cache_write_failed')
    return result(payload, 'refreshed', 'fresh')
