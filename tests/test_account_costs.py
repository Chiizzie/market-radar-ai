from copy import deepcopy
from decimal import Decimal
import pytest
from test_account_sync import provider, NOW
from market_radar_ai.dashboard.account_sync import collect
from market_radar_ai.dashboard.account_costs import extract, reconcile, audit


def row(*, fx='0.9', net='-90.15', fees=None):
    return {'order': {'side': 'BUY', 'currency': 'USD'}, 'fill': {'type': 'TRADE',
        'quantity': '1', 'price_native': '100', 'net_eur': net,
        'cost_evidence': extract({'currency': 'EUR', 'fxRate': fx,
            'taxes': fees if fees is not None else [{'name': 'CURRENCY_CONVERSION_FEE',
                'currency': 'EUR', 'quantity': '0.15', 'chargedAt': NOW.isoformat()}]})}}


def test_collect_retains_private_fx_fees_and_origin_without_changing_net():
    def get(path):
        value = deepcopy(provider(path))
        if 'history' in path:
            value['items'][0]['order']['initiatedFrom'] = 'IOS'
            value['items'][0]['fill']['walletImpact'].update(fxRate=Decimal('0.9'), taxes=[])
        return value
    p = collect(get, NOW)
    r = p['history'][0]
    assert r['order']['initiated_from'] == 'IOS'
    assert r['fill']['cost_evidence']['fx_rate'] == '0.9'
    assert r['fill']['cost_evidence']['fees'] == []
    assert r['fill']['net_eur'] == '-150'
    assert p['cost_audit']['statuses']['unreconciled'] == 1
    assert not p['cost_audit']['broker_cost_model_verified']


def test_missing_fee_array_is_not_an_explicit_zero_charge():
    p = collect(provider, NOW)
    assert p['history'][0]['fill']['cost_evidence']['fees'] is None
    assert p['cost_audit']['statuses']['incomplete'] == 1
    r = row(fees=[], net='-90')
    assert reconcile(r) == 'matched'


@pytest.mark.parametrize('net', ['-90.15', '-111.26'])
def test_cash_arithmetic_can_match_either_fx_direction_but_not_double_count_fees(net):
    r = row(net=net)
    original = deepcopy(r)
    assert reconcile(r) == 'matched'
    assert r == original
    assert reconcile(row(net='-90.30')) == 'unreconciled'


def test_currency_side_ambiguity_and_non_trade_are_explicit():
    r = row(fx='1', net='-100.15')
    assert reconcile(r) == 'ambiguous_fx'
    r['order']['currency'] = 'EUR'
    assert reconcile(r) == 'matched'
    r['order']['side'] = 'SELL'; r['fill']['quantity'] = '-1'; r['fill']['net_eur'] = '99.85'
    assert reconcile(r) == 'matched'
    r['fill']['type'] = 'STOCK_SPLIT'
    assert reconcile(r) == 'non_trade'


@pytest.mark.parametrize('change,expected', [
    ({'currency': 'USD'}, 'unsupported'), ({'quantity': '-0.15'}, 'unsupported'),
    ({'quantity': None}, 'incomplete'), ({'name': None}, 'incomplete'),
])
def test_unsupported_or_incomplete_fee_data_never_passes(change, expected):
    r = row(); r['fill']['cost_evidence']['fees'][0].update(change)
    assert reconcile(r) == expected
    a = audit([r]); assert sum(a['statuses'].values()) == a['rows'] == 1


@pytest.mark.parametrize('wallet', [
    {'fxRate': 'NaN'}, {'fxRate': 0}, {'fxRate': True}, {'taxes': {}},
    {'taxes': [{'currency': 'euro'}]}, {'taxes': [{'quantity': 'Infinity'}]},
    {'taxes': [{'chargedAt': '2026-11-16T15:00:00'}]}, {'taxes': [None]},
])
def test_malformed_source_fields_fail_without_becoming_zero(wallet):
    with pytest.raises((ValueError, ArithmeticError)):
        extract(wallet)
