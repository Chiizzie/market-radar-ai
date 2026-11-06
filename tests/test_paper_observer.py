from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
import pytest
from market_radar_ai.agents.paper_observer import ReferenceObserver
from market_radar_ai.market_data.admission import FxQuote
from test_stock_checks import payload,NOW
from test_evidence_enrichment import reference

def decision(market='stocks',symbol='IBM'):
    return {'packet_id':'a'*64,'candidate_id':market+':'+symbol,'evaluated_at':(NOW-timedelta(seconds=10)).isoformat(),
            'plan':{'symbol':symbol,'currency':'EUR','native_currency':'USD' if market=='stocks' else 'EUR','exit_by':(NOW+timedelta(hours=1)).isoformat()}}

def stock_observer(monkeypatch,p=None):
    p=p or payload();fx=Mock();fx.fetch.return_value=FxQuote.model_validate(p['fx'])
    calls=[]
    def get(url,params,env,session):
        calls.append(url)
        return deepcopy(p['market_clock'] if url.endswith('/clock') else p['quotes'])
    monkeypatch.setattr('market_radar_ai.agents.paper_observer.get',get)
    return ReferenceObserver({},clock=lambda:NOW,session=Mock(),fx_provider=fx),fx,calls

def test_real_stock_adapter_converts_fresh_quotes_and_reuses_fx(monkeypatch):
    p=payload();p['fx']['observed_at']=(NOW-timedelta(minutes=5)).isoformat()
    observer,fx,calls=stock_observer(monkeypatch,p)
    for _ in range(2):
        rows,failures=observer.fetch([decision()])
        assert not failures and rows[0]['quote']['bid']=='90.0' and rows[0]['quote']['ask']=='90.9'
        assert rows[0]['source'].startswith('alpaca_iex:')
    fx.fetch.assert_called_once();assert len(calls)==4

@pytest.mark.parametrize('fault',['stale','crossed','closed','wrong_currency','future','fx_unavailable'])
def test_bad_stock_reference_never_becomes_an_observation(monkeypatch,fault):
    p=payload()
    if fault=='stale':p['quotes']['quotes']['IBM']['t']=(NOW-timedelta(seconds=31)).isoformat()
    if fault=='future':p['quotes']['quotes']['IBM']['t']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='crossed':p['quotes']['quotes']['IBM']['bp']=102
    if fault=='closed':p['market_clock']['is_open']=False
    if fault=='wrong_currency':p['quotes']['currency']='EUR'
    observer,fx,_=stock_observer(monkeypatch,p)
    if fault=='fx_unavailable':fx.fetch.side_effect=RuntimeError('do not expose')
    rows,failures=observer.fetch([decision()])
    assert rows==[] and failures and 'do not expose' not in str(failures)

def test_crypto_uses_native_eur_and_original_receipt_clock():
    ref=reference();ref['request_started_at']=(NOW-timedelta(seconds=1)).isoformat();ref['retrieved_at']=NOW.isoformat()
    observer=ReferenceObserver({},clock=lambda:NOW,crypto_fetch=lambda *a,**k:ref)
    rows,failures=observer.fetch([decision('crypto','XRPEUR')])
    assert not failures and len(rows)==1 and rows[0]['source'].startswith('kraken:')
    assert rows[0]['quote']['observed_at']==NOW.isoformat().replace('+00:00','Z')

def test_currency_identity_cannot_double_convert(monkeypatch):
    observer,_,_=stock_observer(monkeypatch);d=decision();d['plan']['native_currency']='EUR'
    with pytest.raises(ValueError,match='currency_mismatch'):observer.fetch([d])

@pytest.mark.parametrize('available',[True,False])
def test_provider_verification_command_validates_current_capture(monkeypatch,capsys,available):
    import json
    from market_radar_ai.agents import paper_observer
    from market_radar_ai.market_data.reference_quotes import digest
    def capture(pairs,*,clock):
        assert pairs==['XBTEUR']
        ref=reference();now=clock()
        ref['request_started_at']=(now-timedelta(seconds=1)).isoformat()
        ref['retrieved_at']=now.isoformat()
        if not available:
            ref['status']='error';return ref
        ref['requested_pairs']=['XBTEUR']
        meta=ref['payload']['asset_pairs']['result'].pop('XXRPZEUR')
        meta.update(altname='XBTEUR',base='XXBT',wsname='XBT/EUR')
        ref['payload']['asset_pairs']['result']['XXBTZEUR']=meta
        tickers=ref['payload']['tickers']['result']
        tickers['XXBTZEUR']=tickers.pop('XXRPZEUR')
        ref['payload_sha256']=digest(ref['payload'])
        return ref
    monkeypatch.setattr(paper_observer,'capture_quotes',capture)
    monkeypatch.setattr('sys.argv',['paper_observer','--verify-crypto'])
    assert paper_observer.main()==(0 if available else 1)
    result=json.loads(capsys.readouterr().out)
    assert result['model_calls']==result['plans_created']==0
    assert result['trade_authorized'] is False
    assert result['state']==('current_crypto_reference_verified' if available else 'crypto_reference_unavailable')
    if available:assert result['verified_pairs']==['XBTEUR']
