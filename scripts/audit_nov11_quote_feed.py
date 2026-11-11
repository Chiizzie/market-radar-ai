"""Bounded read-only quote audit. No models, messaging, orders or state writes."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def get(path, params, opener, headers):
    request = urllib.request.Request('https://data.alpaca.markets/v2/stocks/' + path
                                    + '?' + urllib.parse.urlencode(params), headers=headers)
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {'state': 'response_too_large'}
            value = json.loads(raw)
            return {'state': 'received', 'http_status': response.status, 'data': value}
    except urllib.error.HTTPError as exc:
        # Provider bodies and credential-bearing request objects never reach logs.
        raw = exc.read(4096)
        try:
            body = json.loads(raw)
            code = body.get('code')
            denied = 'subscription' in str(body.get('message', '')).lower()
        except (ValueError, AttributeError):
            code, denied = None, False
        return {'state': 'http_error', 'http_status': exc.code,
                'provider_code': code if type(code) is int else None,
                'subscription_restriction_reported': denied}
    except (OSError, ValueError):
        return {'state': 'transport_or_response_error'}


def quote_summary(rows, at):
    usable = []
    for row in rows:
        try:
            observed = timestamp(row['t'])
            bid, ask = Decimal(str(row['bp'])), Decimal(str(row['ap']))
            sizes = [Decimal(str(row[k])) for k in ('bs', 'as')]
            if not all(v.is_finite() and v > 0 for v in (bid, ask, *sizes)) or bid > ask:
                continue
            usable.append((observed, row, (ask-bid)/((ask+bid)/2)*10000))
        except (KeyError, ValueError, ArithmeticError, TypeError):
            continue
    usable.sort(key=lambda x: x[0])
    before = [r for r in usable if r[0] <= at]
    after = [r for r in usable if r[0] >= at]
    def item(row):
        return None if row is None else {'quote': row[1], 'spread_bps': str(row[2]),
                                        'seconds_from_reference': (row[0]-at).total_seconds()}
    return {'valid_quotes': len(usable), 'last_at_or_before': item(before[-1] if before else None),
            'first_at_or_after': item(after[0] if after else None),
            'min_bid': str(min(Decimal(str(r[1]['bp'])) for r in usable)) if usable else None,
            'max_bid': str(max(Decimal(str(r[1]['bp'])) for r in usable)) if usable else None}


def run(output):
    if any(os.environ.get(k) for k in ('OPENAI_API_KEY', 'OPEN_API_KEY', 'TELEGRAM_BOT_TOKEN', 'GH_PAPER_TOKEN')):
        raise ValueError('unneeded_credentials_forbidden')
    headers = {'APCA-API-KEY-ID': os.environ['ALPACA_API_KEY'],
               'APCA-API-SECRET-KEY': os.environ['ALPACA_API_SECRET']}
    opener = urllib.request.build_opener(NoRedirect)
    now = datetime.now(timezone.utc)
    report = {'as_of': now.isoformat(), 'purpose': 'retrospective_quote_comparison_only',
              'currency': 'USD', 'model_calls': 0, 'trade_authorized': False,
              'original_outcomes_changed': False, 'latest': {}, 'windows': []}
    for feed in ('iex', 'sip'):
        report['latest'][feed] = get('quotes/latest', {'symbols': 'LRCX,SLM,MTCH,MOS,WU',
                                      'feed': feed, 'currency': 'USD'}, opener, headers)
    windows = [
        ('LRCX', 'entry', '2026-11-11T17:21:57.761434Z'),
        ('LRCX', 'exit', '2026-11-11T17:24:15.513063Z'),
        ('SLM', 'entry', '2026-11-11T17:31:01.257873Z'),
        ('MOS', 'entry', '2026-11-11T17:40:40.801217Z'),
        ('MOS', 'exit', '2026-11-11T18:00:46.949047Z'),
        ('SLM', 'stale_gap', '2026-11-11T17:58:30Z'),
        ('WU', 'stale_gap', '2026-11-11T17:56:00Z'),
    ]
    for symbol, label, value in windows:
        at = timestamp(value)
        start, end = at-timedelta(seconds=5), at+timedelta(seconds=5)
        for feed in ('iex', 'sip'):
            window = {'symbol': symbol, 'label': label, 'reference_at': value, 'feed': feed}
            report['windows'].append(window)
            if end > now-timedelta(minutes=16):
                window['state'] = 'too_recent_for_delayed_historical_audit'
                continue
            params = {'symbols': symbol, 'start': start.isoformat(), 'end': end.isoformat(),
                      'feed': feed, 'currency': 'USD', 'limit': 10000, 'sort': 'asc'}
            window.update(get('quotes', params, opener, headers))
            if window['state'] == 'received':
                data = window['data']
                window['truncated'] = bool(data.get('next_page_token'))
                window['comparison'] = quote_summary(data.get('quotes', {}).get(symbol, []), at)
    end = min(timestamp('2026-11-11T18:02:00Z'), now-timedelta(minutes=16))
    report['historical_sip_bars'] = get('bars', {'symbols': 'LRCX,SLM,MTCH,MOS',
        'start': '2026-11-11T16:00:00Z', 'end': end.isoformat(), 'timeframe': '1Min',
        'feed': 'sip', 'currency': 'USD', 'limit': 10000, 'sort': 'asc'}, opener, headers)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'state': 'audit_recorded', 'latest': {k: v['state'] for k, v in report['latest'].items()},
                      'windows': len(report['windows']), 'model_calls': 0, 'trade_authorized': False}))


if __name__ == '__main__':
    run('artifacts/quote-feed-audit.json')
