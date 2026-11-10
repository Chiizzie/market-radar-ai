"""Private, read-only holding review. Never changes paper results or places orders."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import hashlib
import hmac
import re
import requests

from ..agents.setup_checks import validate_paper_plan
from ..market_data.providers.alpaca_batch import fetch_histories
from .delivery_ledger import DeliveryLedger, GitHubDeliveryStore

POLICY = 'position-monitor-v1'
REASONS = {
    'failed_breakout': 'Two consecutive completed 5-minute candles closed below the original breakout trigger after your entry. Review the failed breakout.',
    'trend_weakening': 'Two completed closes are below the rolling 20-bar volume-weighted price. The original trend condition has weakened.',
    'stop_breached': 'A completed candle closed at or below the original stop. The original price condition is invalidated.',
    'target_reached': 'A completed candle closed at or above the original target. Review your exit.',
    'exit_due': 'The original intraday exit deadline has arrived. The plan is no longer valid for holding overnight.',
    'exit_soon': 'The original intraday exit deadline is within 10 minutes. Prepare to close or explicitly reassess your holding.',
    'data_unavailable': 'Fresh, consecutive completed candles are unavailable. Monitoring cannot confirm the setup; check the broker directly.',
}


def dt(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('aware_time_required')
    return result


def episode(account, position):
    """Reconcile the current long holding, including partial sells and subsequent adds."""
    if not account['history_complete']:
        return None
    rows = [r for r in account['history'] if r['order']['ticker'] == position['ticker'] and r.get('fill')]
    rows.sort(key=lambda r: dt(r['fill']['filled_at']))
    quantity, average, opened = Decimal(0), Decimal(0), None
    for row in rows:
        fill = row['fill']
        if fill['type'] != 'TRADE' or fill['quantity'] is None or fill['price_native'] is None:
            return None  # Corporate actions need their own reconciliation.
        amount, price = abs(Decimal(fill['quantity'])), Decimal(fill['price_native'])
        if amount <= 0 or price <= 0 or row['order']['currency'] != position['currency']:
            return None
        if row['order']['side'] == 'BUY':
            if quantity == 0:
                opened = fill['filled_at']
            average = (average * quantity + price * amount) / (quantity + amount)
            quantity += amount
        else:
            quantity -= amount
            if abs(quantity) < Decimal('0.000001'):
                quantity, average, opened = Decimal(0), Decimal(0), None
            if quantity < 0:
                return None
    if opened is None or abs(quantity - Decimal(position['quantity'])) > Decimal('0.000001'):
        return None
    return {'opened_at': opened, 'entry_native': str(average)}


def linked_plan(decisions, symbol, opened):
    candidates = []
    for d in decisions:
        p = d.get('plan')
        if (d.get('verdict') != 'PAPER_WATCH_FOR_ENTRY' or d.get('paper_only') is not True
                or d.get('trade_authorized') is not False or d.get('live_orders_enabled') is not False
                or d.get('blockers') or not p or d.get('candidate_id') != 'stocks:' + symbol
                or p.get('native_currency') != 'USD' or p.get('symbol') != symbol
                or not re.fullmatch('[a-f0-9]{64}', d.get('packet_id', ''))):
            continue
        approved = dt(d['evaluated_at'])
        # Bind the call available when this holding opened, never a later replacement.
        if not approved <= dt(opened) <= dt(p['expires_at']):
            continue
        if validate_paper_plan(p, now=approved)['state'] != 'PASS':
            continue
        rate = Decimal(p['fx_rate'])
        if not rate.is_finite() or rate <= 0:
            continue
        candidates.append({'packet_id': d['packet_id'], 'approved_at': d['evaluated_at'],
            'trigger_native': str(Decimal(p['entry_eur']) / rate),
            'stop_native': str(Decimal(p['stop_eur']) / rate),
            'target_native': str(Decimal(p['target_eur']) / rate),
            'expires_at': p['expires_at'], 'exit_by': p['exit_by'],
            'invalidation': p['invalidation']})
    return max(candidates, key=lambda p: dt(p['approved_at']), default=None)


def assess(row, result, now):
    plan = row['plan']
    if plan is None:
        return row
    reasons = []
    cutoff = dt(plan['exit_by'])
    if now >= cutoff:
        reasons.append('exit_due')
    elif cutoff - now <= timedelta(minutes=10):
        reasons.append('exit_soon')
    bars = result.candles if result is not None and result.status == 'ok' else []
    fresh = (len(bars) >= 2 and all(c.symbol == row['symbol'] and c.quote_currency == 'USD'
        and c.source == 'alpaca_iex' and c.timestamp + timedelta(minutes=5) <= now for c in bars)
        and timedelta(0) <= now - (bars[-1].timestamp + timedelta(minutes=5)) <= timedelta(minutes=5)
        and bars[-1].timestamp - bars[-2].timestamp == timedelta(minutes=5)
        and all(c.volume > 0 for c in bars[-2:]))
    if not fresh:
        reasons.append('data_unavailable')
    else:
        last = bars[-1]
        row['last_close_native'] = str(last.close)
        row['bar_closed_at'] = (last.timestamp + timedelta(minutes=5)).isoformat()
        # Exclude any candle containing time before the actual purchase.
        post = [c for c in bars if c.timestamp >= dt(row['opened_at'])]
        if post and last.close <= Decimal(plan['stop_native']):
            reasons.append('stop_breached')
        if post and last.close >= Decimal(plan['target_native']):
            reasons.append('target_reached')
        if len(post) >= 2 and all(c.close < Decimal(plan['trigger_native']) for c in post[-2:]):
            reasons.append('failed_breakout')
        trend_ready = len(bars) >= 21 and all(
            b.timestamp - a.timestamp == timedelta(minutes=5) for a, b in zip(bars[-21:], bars[-20:]))
        if not trend_ready:
            reasons.append('data_unavailable')
        if trend_ready and len(post) >= 2:
            below = []
            for window in (bars[-21:-1], bars[-20:]):
                volume = sum(c.volume for c in window)
                weighted = sum(((c.high + c.low + c.close) / 3) * c.volume for c in window)
                below.append(volume > 0 and window[-1].close < weighted / volume)
            if all(below):
                reasons.append('trend_weakening')
    row['reasons'] = reasons
    row['state'] = ('invalidated' if any(r in reasons for r in ('exit_due', 'stop_breached'))
        else 'review_exit' if any(r in reasons for r in ('failed_breakout', 'target_reached'))
        else 'data_unavailable' if 'data_unavailable' in reasons
        else 'weakening' if reasons else 'monitoring')
    return row


def build(account, decisions, *, now, fetch=None):
    if not timedelta(0) <= now - dt(account['generated_at']) <= timedelta(minutes=5):
        raise ValueError('account_not_fresh')
    rows = []
    for p in account['positions']:
        if p['currency'] != 'USD' or not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}_US_EQ', p['ticker']):
            continue
        if p['quantity'] is None or Decimal(p['quantity']) <= 0:
            continue
        e = episode(account, p)
        symbol = p['ticker'].removesuffix('_US_EQ')
        plan = linked_plan(decisions, symbol, e['opened_at']) if e else None
        rows.append({'ticker': p['ticker'], 'symbol': symbol, 'currency': 'USD',
            'opened_at': e['opened_at'] if e else None, 'entry_native': e['entry_native'] if e else None,
            'plan': plan, 'state': 'unlinked', 'reasons': [], 'last_close_native': None, 'bar_closed_at': None})
    symbols = [r['symbol'] for r in rows if r['plan']]
    try:
        observations = fetch(symbols) if symbols and fetch else {}
    except Exception:
        observations = {}
    return {'schema_version': POLICY, 'checked_at': now.isoformat(), 'status': 'ok',
        'notification_status': 'disabled', 'rows': [assess(r, observations.get(r['symbol']), now) for r in rows]}


def render(row, reasons):
    plan = row['plan']
    return '\n'.join(['⚠️ HOLDING REVIEW — ' + row['symbol'],
        'Your actual holding is still reported open. No sell order has been placed.',
        *[REASONS[r] for r in reasons],
        'Last completed close: ' + (('$' + row['last_close_native'] + ' USD at ' +
            dt(row['bar_closed_at']).astimezone(ZoneInfo('Europe/Dublin')).strftime('%H:%M Dublin'))
            if row['last_close_native'] else 'unavailable'),
        f"Original trigger ${Decimal(plan['trigger_native']):.6f} | SL ${Decimal(plan['stop_native']):.6f} | TP ${Decimal(plan['target_native']):.6f} USD",
        'Check your live broker price. These are periodic IEX candle checks, not a protective order or a guaranteed exit.',
        'https://pixel-perfect-replay-32614.lovable.app/opportunity'])


def notify(report, account, *, env, ledger=None, session=None):
    if env.get('SEND_POSITION_MONITOR_TELEGRAM') != 'true':
        return 'disabled'
    secret, token, chat = (env.get(k, '') for k in ('REVIEW_INGEST_SECRET', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'))
    if len(secret) < 32 or not token or not chat.lstrip('-').isdigit():
        return 'unconfirmed'
    ledger = ledger or DeliveryLedger(GitHubDeliveryStore(env.get('GH_PAPER_TOKEN', '')))
    transport, sent, failed = session or requests, False, False
    for row in report['rows']:
        reserved = []
        for reason in row['reasons']:
            # HMAC makes the public dedup key opaque even for known symbols/calls.
            identity = '|'.join([POLICY, account['account_ref'], row['ticker'], row['opened_at'],
                row['plan']['packet_id'], report['checked_at'][:10], reason])
            key = 'research:' + hmac.new(secret.encode(), identity.encode(), hashlib.sha256).hexdigest()
            try:
                ledger.reserve(key)
                reserved.append((key, reason))
            except ValueError as exc:
                if str(exc) != 'delivery_already_attempted_do_not_retry':
                    failed = True
            except Exception:
                failed = True
        if not reserved:
            continue
        try:
            response = transport.post('https://api.telegram.org/bot' + token + '/sendMessage',
                json={'chat_id': chat, 'text': render(row, [r for _, r in reserved]), 'protect_content': True,
                    'link_preview_options': {'is_disabled': True}}, timeout=(5, 10), allow_redirects=False)
            value = response.json()
            if (response.status_code != 200 or value.get('ok') is not True
                    or str(value['result']['chat']['id']) != chat or type(value['result']['message_id']) is not int):
                raise ValueError('invalid_acknowledgement')
            for key, _ in reserved:
                ledger.confirm(key)
            sent = True
        except Exception:
            failed = True  # Never resend an ambiguous delivery.
    return 'unconfirmed' if failed else 'confirmed' if sent else 'none'


def collect_monitor(account, *, env, now):
    try:
        from ..agents.github_paper_tracking import load
        state, _ = load(env.get('GH_PAPER_TOKEN', ''))
        return build(account, state['decisions'], now=now,
            fetch=lambda symbols: fetch_histories(symbols, env=env))
    except Exception:
        return {'schema_version': POLICY, 'checked_at': now.isoformat(), 'status': 'unavailable',
            'notification_status': 'disabled', 'rows': []}
