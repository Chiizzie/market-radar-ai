"""Read-only US equity session evidence; never an order permission or halt check."""
from datetime import datetime, timezone
import os
import re
from zoneinfo import ZoneInfo
import requests

URL = 'https://paper-api.alpaca.markets/v2/calendar'
SOURCE = 'alpaca_us_equity_calendar'
NY = ZoneInfo('America/New_York')


def session_bounds(evidence, *, now):
    """Validate retained evidence again when building/replaying a plan."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    if evidence['version'] != 'us-equity-calendar-v1' or evidence['source'] != SOURCE:
        raise ValueError('calendar_source_invalid')
    observed = datetime.fromisoformat(evidence['observed_at'])
    if observed.tzinfo is None or not 0 <= (now-observed).total_seconds() <= 300:
        raise ValueError('calendar_stale')
    day = now.astimezone(NY).date().isoformat()
    if evidence['date'] != day or evidence['status'] != 'session':
        raise ValueError('calendar_closed_or_unavailable')
    bounds = []
    for key in ('open', 'close'):
        value = evidence[key]
        if not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}', value):
            raise ValueError('calendar_time_invalid')
        bounds.append(datetime.fromisoformat(day+'T'+value).replace(tzinfo=NY))
    start, end = bounds
    if (not start < end or (start.hour,start.minute) < (9,30)
            or (end.hour,end.minute) > (16,0) or start.weekday() >= 5):
        raise ValueError('calendar_session_invalid')
    return start, end


def capture_calendar(*, now=None, session=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    day = now.astimezone(NY).date().isoformat()
    result = dict(version='us-equity-calendar-v1', source=SOURCE,
                  observed_at=now.isoformat(), date=day, status='unavailable')
    try:
        key, secret = os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_API_SECRET')
        if not key or not secret:
            raise ValueError('credentials_missing')
        response = (session or requests).get(URL, params={'start':day, 'end':day},
            headers={'APCA-API-KEY-ID':key, 'APCA-API-SECRET-KEY':secret},
            timeout=15, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError('provider_error')
        rows = response.json()
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError('calendar_payload_invalid')
        if not rows:
            result['status'] = 'closed'
            return result
        row = rows[0]
        if row['date'] != day:
            raise ValueError('calendar_date_mismatch')
        candidate = dict(result, status='session', open=row['open'], close=row['close'])
        session_bounds(candidate, now=now)
        return candidate
    except Exception:
        # Never persist exception text, response bodies or authentication headers.
        return result
