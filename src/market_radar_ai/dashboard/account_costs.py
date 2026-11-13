"""Private fill-cost evidence; never infer zero fees from missing fields."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
import re


STATUSES = ('matched', 'ambiguous_fx', 'unreconciled', 'incomplete', 'unsupported', 'non_trade')
TOLERANCE = Decimal('0.02')


def number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('invalid_cost_evidence')
    d = Decimal(str(value))
    if not d.is_finite() or abs(d) > Decimal('1e12'):
        raise ValueError('invalid_cost_evidence')
    return str(d)


def label(value):
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        raise ValueError('invalid_cost_evidence')
    return value


def currency(value):
    if value is not None and (not isinstance(value, str) or not re.fullmatch('[A-Z]{3}', value)):
        raise ValueError('invalid_cost_evidence')
    return value


def stamp(value):
    if value is not None:
        if not isinstance(value, str):
            raise ValueError('invalid_cost_evidence')
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('invalid_cost_evidence')
    return value


def extract(wallet):
    """Retain the broker's fields with explicit null versus explicit empty list."""
    fx = number(wallet.get('fxRate'))
    if fx is not None and Decimal(fx) <= 0:
        raise ValueError('invalid_cost_evidence')
    raw = wallet.get('taxes')
    if raw is not None and (not isinstance(raw, list) or len(raw) > 50):
        raise ValueError('invalid_cost_evidence')
    fees = None
    if raw is not None:
        fees = []
        for fee in raw:
            if not isinstance(fee, dict):
                raise ValueError('invalid_cost_evidence')
            fees.append({'name': label(fee.get('name')), 'currency': currency(fee.get('currency')),
                         'quantity': number(fee.get('quantity')), 'charged_at': stamp(fee.get('chargedAt'))})
    return {'schema_version': 't212-fill-cost-evidence-v1',
            'wallet_currency': currency(wallet.get('currency')), 'fx_rate': fx, 'fees': fees}


def reconcile(row):
    """Check net cash arithmetic, not execution spread, P/L or fee completeness.

    Trading 212's observed fee entries are signed cash deductions, while
    netValue is a positive magnitude for both buys and sells. Infer cash
    direction from side without changing either stored field. A negative BUY
    net value is also supported; a negative SELL or positive fee is unresolved.
    FX direction must uniquely fit within EUR0.02. This is not a full cost model.
    """
    fill, order = row.get('fill'), row['order']
    if fill is None or fill['type'] != 'TRADE':
        return 'non_trade'
    evidence = fill.get('cost_evidence')
    if evidence is None or evidence['fees'] is None:
        return 'incomplete'
    if evidence['wallet_currency'] != 'EUR' or order['side'] not in ('BUY', 'SELL'):
        return 'unsupported'
    fields = [fill.get('quantity'), fill.get('price_native'), fill.get('net_eur')]
    if any(v is None for v in fields):
        return 'incomplete'
    q, price, net = map(Decimal, fields)
    if q == 0 or price <= 0 or (order['side'] == 'SELL' and net < 0):
        return 'unsupported'
    net_cash = -abs(net) if order['side'] == 'BUY' else net
    fees = Decimal(0)
    for fee in evidence['fees']:
        if fee['quantity'] is None or fee['currency'] is None or fee['name'] is None:
            return 'incomplete'
        if fee['currency'] != 'EUR' or Decimal(fee['quantity']) > 0:
            return 'unsupported'
        fees += Decimal(fee['quantity'])
    gross = abs(q) * price * (1 if order['side'] == 'SELL' else -1)
    if order['currency'] == 'EUR':
        estimates = [gross + fees]
    else:
        if evidence['fx_rate'] is None:
            return 'incomplete'
        fx = Decimal(evidence['fx_rate'])
        estimates = [gross * fx + fees, gross / fx + fees]
    matches = sum(abs(value - net_cash) <= TOLERANCE for value in estimates)
    return 'matched' if matches == 1 else 'ambiguous_fx' if matches > 1 else 'unreconciled'


def audit(history):
    counts = Counter(reconcile(row) for row in history)
    return {'schema_version': 't212-private-cost-audit-v1', 'rows': len(history),
            'statuses': {s: counts[s] for s in STATUSES},
            'tolerance_eur': str(TOLERANCE), 'broker_cost_model_verified': False,
            'scope': 'net_cash_arithmetic_only_not_spread_or_complete_round_trip_cost'}
