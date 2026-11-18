from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from test_stock_checks import payload,NOW
from market_radar_ai.market_data.stock_checks import reuse_catalogue,collect,evaluate
from market_radar_ai.market_data.reference_quotes import digest
from market_radar_ai.market_data.admission import FxQuote

def record():
    p=payload();p['catalogue_candidates']['IBM']=[{'ticker':'IBM_US_EQ','isin':'US4592001014','name':'IBM','currency':'USD','type':'STOCK'}]
    return {'payload':p,'payload_sha256':digest(p)}

@pytest.mark.parametrize('fault',['checksum','expired','future','currency','identity','failure','missing'])
def test_bad_catalogue_never_reused(fault):
    r=record();p=r['payload']
    if fault=='expired':p['retrieved_at']=(NOW-timedelta(seconds=601)).isoformat()
    if fault=='future':p['retrieved_at']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='currency':p['catalogue_candidates']['IBM'][0]['currency']='EUR'
    if fault=='identity':p['catalogue_candidates']['IBM'][0]['ticker']='OTHER_US_EQ'
    if fault=='failure':p['failures']=['catalogue_unavailable']
    if fault=='missing':p['symbols']=[]
    if fault!='checksum':r['payload_sha256']=digest(p)
    else:r['payload_sha256']='broken'
    assert reuse_catalogue(r,['IBM'],now=NOW) is None

def test_metadata_reused_without_reusing_quotes_or_refreshing_its_age(monkeypatch):
    r=record();later=NOW+timedelta(seconds=300)
    class NoFetch:
        def fetch(self):raise AssertionError('must not refetch catalogue')
    calls=[]
    def get(url,params,env,session):
        calls.append(url)
        if url.endswith('/clock'):return {**payload()['market_clock'],'timestamp':later.isoformat()}
        return {'quotes':{'IBM':{**payload()['quotes']['quotes']['IBM'],'t':later.isoformat()}}}
    monkeypatch.setattr('market_radar_ai.market_data.stock_checks.get',get)
    fx=SimpleNamespace(fetch=lambda *a,**kw:FxQuote(native_currency='USD',eur_per_unit='.9',observed_at=later,source='fixture'))
    fresh=collect(['IBM'],env={},clock=lambda:later,catalogue=NoFetch(),catalogue_record=r,fx_provider=fx)
    assert len(calls)==2 and fresh['payload']['catalogue_observed_at']==NOW.isoformat()
    assert fresh['payload']['catalogue_source']=='same_capture_validated_metadata'
    assert evaluate(fresh,now=later)['stocks'][0]['catalogue_status']=='single_candidate_unverified'
    assert reuse_catalogue(fresh,['IBM'],now=NOW+timedelta(seconds=601)) is None
    fresh['payload']['quotes']['quotes']['IBM']['t']=NOW.isoformat();fresh['payload_sha256']=digest(fresh['payload'])
    assert evaluate(fresh,now=later)['stocks'][0]['quote_status']=='unavailable'

def test_empty_and_ambiguous_not_promoted():
    for rows in ([],record()['payload']['catalogue_candidates']['IBM']*2):
        r=record();r['payload']['catalogue_candidates']['IBM']=rows;r['payload_sha256']=digest(r['payload'])
        assert reuse_catalogue(r,['IBM'],now=NOW)[0]['IBM']==rows
        assert evaluate(r,now=NOW)['stocks'][0]['catalogue_status'] in ('not_found','ambiguous')
