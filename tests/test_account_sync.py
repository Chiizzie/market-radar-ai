from datetime import datetime, timezone
import pytest
from market_radar_ai.dashboard.account_sync import collect, safe_path, deliver, decimal
NOW=datetime(2026,11,6,10,tzinfo=timezone.utc)
ORDER={'id':1,'ticker':'TEST_US_EQ','instrument':{'ticker':'TEST_US_EQ','currency':'USD','name':'Synthetic'},'side':'BUY','status':'FILLED','createdAt':NOW.isoformat(),'quantity':2,'filledQuantity':2,'currency':'USD'}
def provider(path):
 if path.endswith('summary'):return {'id':123,'currency':'EUR','totalValue':200,'cash':{'availableToTrade':40},'investments':{'totalCost':150,'currentValue':160,'unrealizedProfitLoss':10}}
 if path.endswith('positions'):return [{'instrument':ORDER['instrument'],'quantity':2,'walletImpact':{'currency':'EUR','totalCost':150,'currentValue':160,'unrealizedProfitLoss':10}}]
 if path.endswith('/orders'):return []
 return {'items':[{'order':ORDER,'fill':{'id':2,'filledAt':NOW.isoformat(),'type':'TRADE','price':82,'quantity':2,'walletImpact':{'currency':'EUR','netValue':-150}}}], 'nextPagePath':None}
def test_normalized_account_keeps_eur_cash_separate_from_native_price():
 p=collect(provider,NOW)
 assert p['positions'][0]['cost_eur']=='150'
 assert p['history'][0]['fill']['net_eur']=='-150'
 assert p['history'][0]['fill']['price_native']=='82'
 assert p['summary']['realized_eur'] is None
 assert p['history_complete'] and p['read_only']
 assert 'id' not in p and '123' not in p['account_ref']
@pytest.mark.parametrize('path',['https://evil.test/api/v0/equity/orders','//evil.test/api/v0/equity/orders','/api/v0/equity/orders/market','/api/v0/equity/history/orders?limit=50&cursor=x','/api/v0/equity/history/orders?limit=50#x'])
def test_paths_never_send_auth_elsewhere(path):
 with pytest.raises(ValueError):safe_path(path)
def test_paginated_history_not_silently_truncated():
 paths=[]
 def get(path):
  paths.append(path);p=provider(path)
  if '?limit=50' in path and '&cursor' not in path:p['nextPagePath']='/api/v0/equity/history/orders?limit=50&cursor=2'
  elif '&cursor' in path:p['items']=[]
  return p
 p=collect(get,NOW,sleep=lambda _:None)
 assert len(paths)==5 and p['history_complete']
def test_non_eur_account_is_not_labelled_eur():
 def get(path):
  p=provider(path)
  if path.endswith('summary'):p['currency']='USD'
  return p
 with pytest.raises(ValueError,match='currency'):collect(get,NOW)
def test_redirect_disabled_and_only_signed_private_destination():
 calls=[]
 class Reply:
  status_code=200
  def json(self):return {'ok':True}
 def post(url,**kw):calls.append((url,kw));return Reply()
 deliver(collect(provider,NOW),'x'*32,NOW,post=post)
 assert calls[0][0].endswith('/api/public/account/ingest')
 assert calls[0][1]['allow_redirects'] is False
 assert calls[0][1]['headers']['X-Signature'].startswith('sha256=')
def test_non_finite_rejected():
 with pytest.raises(ValueError):decimal('NaN')
