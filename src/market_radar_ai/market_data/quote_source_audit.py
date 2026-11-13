"""Read-only IEX/SIP comparison; never supplies quotes to a trading experiment."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import time

import requests

URL = 'https://data.alpaca.markets/v2/stocks/quotes/latest'
SYMBOL = re.compile(r'[A-Z][A-Z0-9.\-]{0,14}')
PROTOCOL = {'version': 'reference-feed-audit-v1', 'feeds': ['iex', 'sip'],
            'rounds': 3, 'interval_seconds': 5, 'maximum_symbols': 8,
            'maximum_quote_age_seconds': 30, 'maximum_spread_bps': '20',
            'selection': 'SPY_control_plus_recent_worker_quote_failures',
            'strategy_input': False, 'trade_authorized': False}
PROTOCOL_ID = hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def aware(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('aware_quote_required')
    return at


def classify_quote(symbol, payload, *, received):
    row = {'symbol': symbol, 'received_at': received.isoformat(), 'state': 'malformed_quote'}
    try:
        if payload.get('currency', 'USD') != 'USD':
            return {**row, 'state': 'wrong_currency'}
        if symbol not in payload.get('quotes', {}):
            return {**row, 'state': 'missing_quote'}
        quote = payload['quotes'][symbol]
        at = aware(quote['t'])
        age = (received-at).total_seconds()
        bid, ask, bs, az = [Decimal(str(quote[key])) for key in ('bp', 'ap', 'bs', 'as')]
        if not all(x.is_finite() and x > 0 for x in (bid, ask, bs, az)):
            return {**row, 'state': 'invalid_price_or_size'}
        if bid > ask:
            return {**row, 'state': 'crossed_quote'}
        spread = (ask-bid)/((ask+bid)/2)*10000
        state = ('future_quote' if age < 0 else 'stale_quote' if age > 30
                 else 'wide_reference_quote' if spread > 20 else 'current_reference_quote')
        return {**row, 'state': state, 'quote_at': at.isoformat(), 'age_seconds': age,
                'bid_usd': str(bid), 'ask_usd': str(ask), 'spread_bps': str(spread)}
    except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
        return row


def fetch_feed(feed, symbols, *, env, transport, clock):
    if feed not in PROTOCOL['feeds']:
        raise ValueError('audit_feed_not_allowed')
    if not env.get('ALPACA_API_KEY') or not env.get('ALPACA_API_SECRET'):
        return {'feed': feed, 'state': 'credentials_missing', 'rows': []}
    started = clock()
    try:
        with transport.get(URL, params={'symbols': ','.join(symbols), 'feed': feed, 'currency': 'USD'},
            headers={'APCA-API-KEY-ID': env['ALPACA_API_KEY'], 'APCA-API-SECRET-KEY': env['ALPACA_API_SECRET']},
            timeout=(5, 10), allow_redirects=False, stream=True) as response:
            code = response.status_code
            raw = bytearray()
            for part in response.iter_content(65536):
                raw.extend(part)
                if len(raw) > 500000:
                    raise ValueError('audit_payload_capacity')
        received = clock()
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            payload = None
        state = ('available' if code == 200 else 'authentication_rejected' if code == 401
                 else 'forbidden_unclassified' if code == 403 else 'rate_limited' if code == 429
                 else 'provider_http_error')
        if code == 403 and isinstance(payload, dict):
            message = payload.get('message')
            if (payload.get('code') == 42210000 and isinstance(message, str)
                    and 'subscription does not permit querying recent sip data' in message[:1000].lower()):
                state = 'subscription_not_permitted'
        if code == 200 and not isinstance(payload, dict):
            state = 'invalid_payload'
        return {'feed': feed, 'state': state, 'http_status': code,
                'requested_at': started.isoformat(), 'received_at': received.isoformat(),
                'response_sha256': hashlib.sha256(raw).hexdigest(),
                'rows': [classify_quote(s, payload, received=received) for s in symbols] if state == 'available' else []}
    except requests.RequestException:
        return {'feed': feed, 'state': 'transport_unavailable', 'rows': []}
    except (ValueError, TypeError, AttributeError):
        return {'feed': feed, 'state': 'invalid_payload', 'rows': []}


def run(health, *, env, transport=None, clock=lambda: datetime.now(timezone.utc), sleep=time.sleep):
    if any(env.get(k) for k in ('OPENAI_API_KEY', 'OPEN_API_KEY', 'GH_BUDGET_TOKEN',
                               'GH_PAPER_TOKEN', 'TELEGRAM_BOT_TOKEN')):
        raise ValueError('unneeded_credentials_forbidden')
    source = health.get('comparison', health)
    failures = source.get('recent_quote_failures', [])
    symbols = ['SPY']
    for row in reversed(failures):
        symbol = row.get('symbol')
        if isinstance(symbol, str) and SYMBOL.fullmatch(symbol) and symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) == PROTOCOL['maximum_symbols']:
            break
    started = clock()
    samples, terminal, pairs = [], {}, []
    transport = transport or requests.Session()
    for round_id in range(PROTOCOL['rounds']):
        batch = {}
        for feed in PROTOCOL['feeds']:
            if feed in terminal:
                sample = {'feed': feed, 'state': terminal[feed], 'rows': [], 'request_skipped': True}
            else:
                sample = fetch_feed(feed, symbols, env=env, transport=transport, clock=clock)
                if sample['state'] in ('credentials_missing', 'authentication_rejected',
                    'forbidden_unclassified', 'subscription_not_permitted', 'rate_limited'):
                    terminal[feed] = sample['state']
            samples.append({'round': round_id, **sample})
            batch[feed] = {r['symbol']: r for r in sample['rows']}
        for symbol in symbols:
            iex, sip = batch['iex'].get(symbol), batch['sip'].get(symbol)
            pair = {'round': round_id, 'symbol': symbol,
                    'iex_state': iex['state'] if iex else None, 'sip_state': sip['state'] if sip else None}
            if iex and sip and 'bid_usd' in iex and 'bid_usd' in sip:
                im = (Decimal(iex['bid_usd'])+Decimal(iex['ask_usd']))/2
                sm = (Decimal(sip['bid_usd'])+Decimal(sip['ask_usd']))/2
                pair['sip_minus_iex_mid_bps'] = str((sm-im)/im*10000)
                pair['receipt_separation_seconds'] = abs((aware(iex['received_at'])-aware(sip['received_at'])).total_seconds())
            pairs.append(pair)
        if round_id < PROTOCOL['rounds']-1 and len(terminal) < len(PROTOCOL['feeds']):
            sleep(PROTOCOL['interval_seconds'])
    summaries = {}
    for feed in PROTOCOL['feeds']:
        selected = [s for s in samples if s['feed'] == feed]
        summaries[feed] = {'requests': sum(not s.get('request_skipped') for s in selected),
                          'request_states': dict(Counter(s['state'] for s in selected)),
                          'quote_states': dict(Counter(r['state'] for s in selected for r in s['rows']))}
    return {'schema_version': 'reference-feed-audit-v1', 'protocol_id': PROTOCOL_ID, 'protocol': PROTOCOL,
            'as_of': clock().isoformat(), 'started_at': started.isoformat(), 'symbols': symbols,
            'prior_worker_quote_failures': len(failures), 'feeds': summaries, 'samples': samples, 'pairs': pairs,
            'dataset_kind': 'diagnostic', 'model_calls': 0, 'trade_authorized': False, 'strategy_input': False,
            'note': 'Separate read-only feed comparison after the worker. IEX and SIP use the same provider. '
                    'Different receipt times are retained; this does not replay earlier missing quotes or prove broker execution. '
                    'No feed subscription, strategy/source policy, entry gate, budget or historical outcome is changed.'}


def main():
    import argparse
    import os
    from pathlib import Path
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--health', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.health.stat().st_size > 500000:
        raise ValueError('worker_health_capacity')
    result = run(json.loads(args.health.read_text()), env=os.environ)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'state': 'reference_feed_audit_recorded', 'symbols': result['symbols'],
                      'feeds': result['feeds'], 'model_calls': 0, 'strategy_input': False}))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write('\n### Reference feed audit (no strategy change)\n\n')
            for feed, summary in result['feeds'].items():
                f.write('- '+feed.upper()+': '+json.dumps(summary)+'\n')
            f.write('\nSource gaps remain visible. No delayed or substituted quote enters the existing experiment.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
