from market_radar_ai.market_data.broker_check import check
from market_radar_ai.market_data.providers.catalogues import Trading212Catalogue

class Client:
    def __init__(self): self.urls=[]
    def get_json(self,url):
        self.urls.append(url)
        if url.endswith('/instruments'):
            return [dict(ticker='NVDA_US_EQ', isin='fixture-isin', currencyCode='USD',
                         type='STOCK',name='NVIDIA',workingScheduleId=7)]
        return [dict(id=2,name='NASDAQ',workingSchedules=[{'id':7}])]

def test_only_metadata_and_no_trade_authorization():
    client=Client();result=check(Trading212Catalogue(client))
    assert result['state']=='catalogue_received'
    assert result['candidates'][0]['exchanges']==[{'id':2,'name':'NASDAQ'}]
    assert client.urls==[Trading212Catalogue.URL,'https://live.trading212.com/api/v0/equity/metadata/exchanges']
    assert result['trade_authorized'] is False and result['account_type_verified'] is False
    assert result['model_calls']==0

def test_provider_error_does_not_expose_credentials():
    class Bad:
        def fetch(self): raise RuntimeError('secret-material')
    result=check(Bad())
    assert result['state']=='blocked' and result['candidates']==[]
    assert 'secret-material' not in str(result)
