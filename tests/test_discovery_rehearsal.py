from copy import deepcopy
from datetime import datetime, timezone
import pytest
from market_radar_ai.market_data.rehearsal import validated_universe
from market_radar_ai.market_data.models import ProviderResult, Instrument
from market_radar_ai.market_data.providers.stocks import StockDirectory

NOW=datetime(2026,11,2,20,tzinfo=timezone.utc)


def inputs():
    stocks={'status':'ok','retrieved_at':NOW.isoformat(),'stocks':['MSFT'],
        'sources':[{'url':StockDirectory.BASE+f,'file_creation_marker':'File Creation Time: 1102202617:00',
                    'listings':[{'symbol':'MSFT'}]} for f in ['nasdaqlisted.txt','otherlisted.txt']]}
    crypto=ProviderResult(provider='kraken_catalogue',retrieved_at=NOW,instruments=[
        Instrument(symbol='XBTEUR',asset_class='crypto',quote_currency='EUR',venue='Kraken')])
    return stocks,crypto


def test_complete_discovery_validates_but_does_not_grant_eligibility():
    s,c=inputs()
    assert validated_universe(s,c,now=NOW)=={'stocks':['MSFT'],'crypto':['XBTEUR']}


@pytest.mark.parametrize('marker',['File Creation Time: 1010202617:00','File Creation Time: 1103202617:00','File Creation Time: broken'])
def test_stale_future_or_malformed_directory_rejected(marker):
    s,c=inputs();s['sources'][0]['file_creation_marker']=marker
    with pytest.raises(ValueError):validated_universe(s,c,now=NOW)


def test_partial_and_membership_mismatch_rejected():
    s,c=inputs();s['status']='error'
    with pytest.raises(ValueError):validated_universe(s,c,now=NOW)
    s,c=inputs();s['stocks']=['AAPL']
    with pytest.raises(ValueError):validated_universe(s,c,now=NOW)


def test_pipeline_exports_real_contract_without_model_or_trade_calls(tmp_path):
    import json
    from datetime import timedelta
    from market_radar_ai.market_data.rehearsal import run
    from market_radar_ai.market_data.models import Candle
    now=datetime.now(timezone.utc)
    s,c=inputs()
    s['retrieved_at']=now.isoformat()
    for source in s['sources']:
        source['file_creation_marker']='File Creation Time: '+now.strftime('%m%d%Y%H:%M')
        source['excluded']=[]
    c=c.model_copy(update={'retrieved_at':now})
    class Stocks:
        def discover(self):return s
    class Crypto:
        def discover_eur(self):return c
    def fetch(symbol):
        provider='kraken' if symbol=='XBTEUR' else 'yahoo_finance'
        return ProviderResult(provider=provider,retrieved_at=now,candles=[Candle(
            symbol=symbol,interval='5m',timestamp=now-timedelta(minutes=5),open=100,high=101,
            low=99,close=100,volume=10,quote_currency='EUR',source=provider)])
    report=run(tmp_path,stock_directory=Stocks(),crypto_catalogue=Crypto(),stock_fetch=fetch,crypto_fetch=fetch)
    assert report['pipeline_completed'] and report['data_rehearsal_passed']
    dashboard=json.loads((tmp_path/'dashboard.json').read_text())
    assert dashboard['coverage']['stocks']['attempted']==1
    assert dashboard['live_orders_enabled'] is False
    assert dashboard['agents']['reports']==[]
    assert not report['trading_ready']
