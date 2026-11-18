"""Bounded discovery features and a timestamp-preserving cross-run checkpoint.

Current daily-bar volume / previous daily-bar volume is a discovery proxy, NOT
same-time historical relative volume or a trade qualification measurement.
"""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
VERSION = 'relative-activity-v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def load_checkpoint(path, *, now):
    if path is None:
        return {}, 'disabled'
    try:
        path = Path(path)
        if not path.exists():
            return {}, 'cold_start'
        if path.stat().st_size > 4_000_000:
            raise ValueError('oversize')
        envelope = json.loads(path.read_text())
        body = envelope['payload']
        if sha256(canonical(body).encode()).hexdigest() != envelope['sha256']:
            raise ValueError('checksum')
        at = datetime.fromisoformat(body['retrieved_at'])
        if (body['schema_version'] != VERSION or body['feed'] != 'iex'
                or at.tzinfo is None or not 0 <= (now-at).total_seconds() <= 1800
                or at.astimezone(NY).date() != now.astimezone(NY).date()
                or not isinstance(body['snapshots'], dict) or len(body['snapshots']) > 20000):
            raise ValueError('invalid_checkpoint')
        return body['snapshots'], 'reused'
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        return {}, 'invalid_or_expired'


def save_checkpoint(path, snapshots, *, now):
    if path is None:
        return 'disabled'
    body = {'schema_version': VERSION, 'feed': 'iex',
            'retrieved_at': now.isoformat(), 'snapshots': snapshots}
    text = canonical({'payload': body, 'sha256': sha256(canonical(body).encode()).hexdigest()})
    if len(text.encode()) > 4_000_000:
        return 'capacity_exceeded'
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name+'.tmp')
        temporary.write_text(text)
        temporary.replace(path)
        return 'saved'
    except OSError:
        return 'write_failed'


def measurements(price, volume, previous_close, previous_volume, *, at, prior):
    relative = None
    previous_volume_value = None
    try:
        pv = Decimal(str(previous_volume))
        if pv.is_finite() and pv > 0:
            relative = float(volume/pv)
            previous_volume_value = str(pv)
    except (ValueError, ArithmeticError):
        pass
    acceleration = None
    acceleration_status = 'missing_prior_observation'
    previous_observation = None
    if isinstance(prior, dict):
        acceleration_status = 'invalid_or_stale_prior_observation'
        try:
            previous_at = datetime.fromisoformat(prior['observed_at'])
            prior_price = Decimal(str(prior['price']))
            if (previous_at.tzinfo is not None and 0 < (at-previous_at).total_seconds() <= 1800
                    and previous_at.astimezone(NY).date() == at.astimezone(NY).date()
                    and prior_price.is_finite() and prior_price > 0):
                acceleration = float((price/prior_price-1)*100)
                previous_observation = {'observed_at': previous_at.isoformat(), 'price': str(prior_price)}
                acceleration_status = 'observed_between_snapshots'
            elif previous_at.tzinfo is not None and previous_at == at:
                acceleration_status = 'same_trade_timestamp'
        except (ValueError, TypeError, KeyError, ArithmeticError):
            pass
    change, turnover = float((price/previous_close-1)*100), float(price*volume)
    liquidity = min(math.log10(max(turnover/500_000, 1))*3, 9)
    score = (liquidity + min(relative*4, 12) if relative is not None else liquidity)
    score += min(abs(change), 3) - min(max(abs(change)-5, 0)*1.5, 30)
    if acceleration is not None:
        score += min(abs(acceleration)*3, 9)
    values = (relative, acceleration, change, turnover, score)
    if any(v is not None and not math.isfinite(v) for v in values):
        raise ValueError('nonfinite_snapshot_measurement')
    return {'observed_at': at.isoformat(), 'price': str(price),
            'daily_bar_volume': str(volume), 'previous_daily_bar_volume': previous_volume_value,
            'previous_close': str(previous_close), 'prior_observation': previous_observation,
            'turnover_usd': round(turnover, 2), 'day_change_pct': round(change, 6),
            'relative_session_volume': round(relative, 6) if relative is not None else None,
            'acceleration_pct': round(acceleration, 6) if acceleration is not None else None,
            'acceleration_status': acceleration_status,
            'score': round(score, 6), 'ranking_policy': VERSION}
