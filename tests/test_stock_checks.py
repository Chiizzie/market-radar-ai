from copy import deepcopy
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from types import SimpleNamespace
import pytest
from market_radar_ai.market_data.stock_checks import assess,collect,evaluate
from market_radar_ai.market_data.reference_quotes import digest
from market_radar_ai.market_data.admission import FxQuote
NOW=datetime(2026,11,4,16,tzinfo=timezone.utc)
def payload():
    return {'schema_version':'stock-reference-checks-v1','symbols':['IBM'],'trade_authorized':False,
      'retrieved_at':NOW.isoformat(),'market_clock':{'timestamp':NOW.isoformat(),'is_open':True,
      'next_open':(NOW+timedelta(days=1)).isoformat(),'next_close':(NOW+timedelta(hours=5)).isoformat()},
      'quotes':{'quotes':{'IBM':{'t':NOW.isoformat(),'bp':100,'ap':101,'bs':3,'as':4}}},
      'fx':{'native_currency':'USD','eur_per_unit':'0.9','source':'test','observed_at':NOW.isoformat()},
      'catalogue_candidates':{'IBM':[{'ticker':'IBM_US_EQ','isin':'test'}]}}
def test_current_references_convert_without_authorizing_trade():
    r=assess(payload(),now=NOW);s=r['stocks'][0]
    assert r['market_clock']['status']=='open' and s['indicative_bid_eur']=='90.0'
    assert not s['eligibility_verified'] and not s['broker_executable'] and not r['trade_authorized']
    assert s['catalogue_status']=='single_candidate_unverified'
@pytest.mark.parametrize('fault',['stale','future','crossed','nan','zero','missing','currency'])
def test_bad_quotes_never_converted(fault):
    p=payload();q=p['quotes']['quotes']['IBM']
    if fault=='stale':q['t']=(NOW-timedelta(seconds=31)).isoformat()
    if fault=='future':q['t']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='crossed':q['bp']=102
    if fault=='nan':q['ap']='NaN'
    if fault=='zero':q['as']=0
    if fault=='missing':p['quotes']['quotes']={}
    if fault=='currency':p['quotes']['currency']='EUR'
    r=assess(p,now=NOW)['stocks'][0]
    assert r['quote_status']=='unavailable' and 'indicative_bid_eur' not in r
def test_stale_fx_clock_and_ambiguous_catalogue_remain_blocked():
    p=payload();p['fx']['observed_at']=(NOW-timedelta(minutes=16)).isoformat()
    p['market_clock']['timestamp']=(NOW-timedelta(seconds=61)).isoformat()
    p['catalogue_candidates']['IBM']*=2
    r=assess(p,now=NOW)
    assert r['fx_status']=='unavailable_or_stale' and r['market_clock']['status']=='unavailable'
    assert r['stocks'][0]['catalogue_status']=='ambiguous'
    assert 'indicative_bid_eur' not in r['stocks'][0]
def test_checksum_and_capture_expiry():
    p=payload();r={'payload':p,'payload_sha256':digest(p)}
    with pytest.raises(ValueError):evaluate(r,now=NOW+timedelta(seconds=61))
    p['symbols']=['OTHER']
    with pytest.raises(ValueError):evaluate(r,now=NOW)
def test_closed_market_not_open_even_with_quotes():
    p=payload();p['market_clock']['is_open']=False
    assert 'regular_session_not_confirmed_open' in assess(p,now=NOW)['stocks'][0]['remaining_blockers']
def test_missing_providers_redact_and_preserve_unknowns():
    class Broken:
        def fetch(self,*a,**k):raise ValueError('secret should not be persisted')
    r=collect(['IBM'],env={},clock=lambda:NOW,catalogue=Broken(),fx_provider=Broken())
    assert 'secret' not in str(r)
    assert len(r['payload']['failures'])==4
    assert evaluate(r,now=NOW)['stocks'][0]['quote_status']=='unavailable'
