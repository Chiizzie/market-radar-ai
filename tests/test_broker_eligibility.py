from copy import deepcopy
from datetime import timedelta
import pytest
from test_paper_planner import inputs, NOW
from market_radar_ai.market_data.broker_eligibility import assess_nvda


def test_exact_identity_does_not_imply_account_permission():
    cat=inputs()[1]
    cat.update(account_type_verified=True,eligibility={'eligibility_verified':True})
    r=assess_nvda(cat,now=NOW)
    assert r['catalogue_identity_verified']
    assert r['account_type_status']=='unknown' and not r['eligibility_verified']
    assert not r['trade_authorized']


@pytest.mark.parametrize('fault',['isin','ticker','currencyCode','type','exchange','duplicate','stale','future'])
def test_wrong_ambiguous_or_stale_identity_fails(fault):
    cat=inputs()[1];row=cat['candidates'][0]
    if fault in ('isin','ticker','currencyCode','type'):row[fault]='wrong'
    if fault=='exchange':row['exchanges']=[{'name':'OTHER'}]
    if fault=='duplicate':cat['candidates'].append(deepcopy(row))
    if fault=='stale':cat['observed_at']=(NOW-timedelta(seconds=601)).isoformat()
    if fault=='future':cat['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
    assert not assess_nvda(cat,now=NOW)['catalogue_identity_verified']
