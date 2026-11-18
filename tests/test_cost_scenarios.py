import pytest
from market_radar_ai.agents.cost_scenarios import fx_scenarios


def test_costs_use_distinct_entry_and_exit_notionals():
    r=fx_scenarios('500','550')
    assert r['scenarios']['convert_on_entry_and_exit_eur']=='1.5750'
    assert r['scenarios']['convert_on_entry_only_eur']=='0.7500'
    assert r['scenarios']['convert_on_exit_only_eur']=='0.8250'
    assert not r['costs_verified'] and r['account_currency_route']=='unknown'

@pytest.mark.parametrize('value',['NaN','Infinity','-1'])
def test_invalid_cost_inputs_rejected(value):
    with pytest.raises(ValueError):fx_scenarios(value,500)
