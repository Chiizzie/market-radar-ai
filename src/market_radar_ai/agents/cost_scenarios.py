"""Explicit paper cost scenarios, not account-specific executable costs."""
from decimal import Decimal

FX_RATE = Decimal('0.0015')
SOURCE = 'https://www.trading212.com/terms/invest'


def fx_scenarios(entry_notional_eur, exit_notional_eur):
    amounts = [Decimal(str(x)) for x in (entry_notional_eur, exit_notional_eur)]
    if any(not x.is_finite() or x < 0 for x in amounts):
        raise ValueError('finite_nonnegative_notionals_required')
    entry, exit_value = amounts
    return dict(version='paper-fx-scenarios-v1', schedule_source=SOURCE,
        schedule_checked='2026-11-03', fx_fee_rate=str(FX_RATE),
        account_currency_route='unknown', costs_verified=False,
        scenarios={
            'convert_on_entry_and_exit_eur':str((entry+exit_value)*FX_RATE),
            'convert_on_entry_only_eur':str(entry*FX_RATE),
            'convert_on_exit_only_eur':str(exit_value*FX_RATE),
            'no_conversion_during_trade_eur':'0'},
        excluded_costs=['spread','slippage','applicable_taxes_and_levies'],
        note='FX component only. No-conversion excludes earlier funding or later withdrawal conversions. Sale notional may differ from entry; route and applicable schedule require confirmation.')
