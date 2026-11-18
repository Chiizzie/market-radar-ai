"""Bounded single-symbol IEX bars for generic research, never broker execution."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
import re
from zoneinfo import ZoneInfo

import requests
from ..models import Candle, ProviderResult, ValidationIssue

SYMBOL = re.compile(r'[A-Z][A-Z0-9.\-]{0,14}')
NY = ZoneInfo('America/New_York')


def parse_bars(data, *, symbol, start, end, received):
    if not isinstance(data, dict) or data.get('symbol') != symbol:
        raise ValueError('symbol_mismatch')
    if data.get('next_page_token'):
        raise ValueError('pagination_incomplete')
    raw = data.get('bars')
    if raw is None:
        raw = []
    if 'bars' not in data or not isinstance(raw, list) or len(raw) > 1000:
        raise ValueError('invalid_bars')
    rows, previous = [], None
    for bar in raw:
        at = datetime.fromisoformat(bar['t'].replace('Z', '+00:00'))
        if at.tzinfo is None or not start <= at <= end or (previous and at <= previous):
            raise ValueError('bar_time_or_order_invalid')
        if at.second or at.microsecond or at.minute % 5:
            raise ValueError('bar_alignment_invalid')
        previous = at
        # Inclusive provider end may contain the in-progress interval.
        if at + timedelta(minutes=5) > end:
            continue
        values = {k: Decimal(str(bar[v])) for k, v in
                  [('open', 'o'), ('high', 'h'), ('low', 'l'), ('close', 'c'), ('volume', 'v')]}
        if not all(v.is_finite() for v in values.values()):
            raise ValueError('nonfinite_bar')
        rows.append(Candle(symbol=symbol, timestamp=at, interval='5m',
                           quote_currency='USD', source='alpaca_iex', **values))
    return ProviderResult(provider='alpaca_iex', retrieved_at=received, candles=rows)


class AlpacaIexProvider:
    def __init__(self, *, session=None, env=None, clock=lambda: datetime.now(timezone.utc)):
        self.session = session or requests.Session()
        self.env = os.environ if env is None else env
        self.clock = clock

    def fetch_history(self, symbol):
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('aware_clock_required')
        reason = 'invalid_symbol'
        try:
            if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
                raise ValueError()
            reason = 'credentials_missing'
            key, secret = self.env.get('ALPACA_API_KEY'), self.env.get('ALPACA_API_SECRET')
            if not key or not secret:
                raise ValueError()
            local = now.astimezone(NY)
            start = local.replace(hour=9, minute=30, second=0, microsecond=0)
            end = min(now, local.replace(hour=16, minute=0, second=0, microsecond=0))
            if local.weekday() >= 5 or end <= start:
                return ProviderResult(provider='alpaca_iex', retrieved_at=now, candles=[],
                    issues=[ValidationIssue(code='regular_session_not_started',
                        message='Regular-session capture deliberately not requested before open or on weekends',
                        symbol=symbol)])
            if end < start + timedelta(minutes=5):
                return ProviderResult(provider='alpaca_iex', retrieved_at=now, candles=[],
                    issues=[ValidationIssue(code='regular_session_warmup',
                        message='Waiting for the first completed five-minute regular-session candle',
                        symbol=symbol)])
            # Fixed data-only host/path suffix, no redirects, pagination or fallback.
            reason = 'transport_failure'
            with self.session.get(f'https://data.alpaca.markets/v2/stocks/{symbol}/bars',
                    params={'timeframe': '5Min', 'start': start.isoformat(), 'end': end.isoformat(),
                            'feed': 'iex', 'currency': 'USD', 'adjustment': 'raw', 'asof': '-',
                            'sort': 'asc', 'limit': 1000},
                    headers={'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret},
                    timeout=(5, 15), allow_redirects=False, stream=True) as response:
                reason = 'provider_http_error'
                if response.status_code != 200:
                    raise ValueError()
                body = bytearray()
                reason = 'response_too_large'
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > 1_000_000:
                        raise ValueError()
            reason = 'invalid_provider_payload'
            return parse_bars(json.loads(body), symbol=symbol, start=start, end=end, received=self.clock())
        except Exception:
            # Never serialize auth headers, provider bodies or exception text.
            return ProviderResult(provider='alpaca_iex', retrieved_at=self.clock(), status='error',
                issues=[ValidationIssue(code=reason, message='Alpaca IEX capture unavailable', symbol=symbol)])
