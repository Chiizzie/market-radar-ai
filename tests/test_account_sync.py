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


@pytest.mark.parametrize('failure', ['timeout', 'connection'])
def test_history_retry_reduces_page_without_moving_cursor(failure):
 import json
 import requests
 from urllib.parse import urlsplit, parse_qs
 from market_radar_ai.dashboard.account_sync import Reader
 from test_scanner_audit_repairs import Reply, Session
 error=requests.ReadTimeout('private') if failure=='timeout' else requests.ConnectionError('private')
 session=Session([error,Reply(body=json.dumps({'items':[], 'nextPagePath':None}).encode())])
 waits=[]
 reader=Reader('key','secret',session=session,sleep=waits.append)
 assert reader('/api/v0/equity/history/orders?limit=50&cursor=123')=={'items':[], 'nextPagePath':None}
 assert parse_qs(urlsplit(session.calls[1][0]).query)=={'limit':['20'],'cursor':['123']}
 assert reader.retries==1 and reader.history_page_reductions==1 and waits==[5]


def test_history_fallback_continues_all_pages_without_dropping_rows():
 import json
 import requests
 from copy import deepcopy
 from market_radar_ai.dashboard.account_sync import Reader
 from test_scanner_audit_repairs import Reply, Session
 first=deepcopy(provider('/api/v0/equity/history/orders?limit=50'))
 first['nextPagePath']='/api/v0/equity/history/orders?limit=20&cursor=2'
 second=deepcopy(provider('/api/v0/equity/history/orders?limit=20&cursor=2'))
 second['items'][0]['order']['id']=2
 second['items'][0]['fill']['id']='second'
 answers=[Reply(body=json.dumps(provider(path)).encode()) for path in
          ['/api/v0/equity/account/summary','/api/v0/equity/positions','/api/v0/equity/orders']]
 answers += [requests.ReadTimeout('private'),Reply(body=json.dumps(first).encode()),
             Reply(body=json.dumps(second).encode())]
 session=Session(answers)
 result=collect(Reader('key','secret',session=session,sleep=lambda _:None),NOW,sleep=lambda _:None)
 assert result['history_complete'] and len(result['history'])==2
 assert [r['fill']['id'] for r in result['history']]==['2','second']
 assert session.calls[-1][0].endswith('?limit=20&cursor=2')


def test_history_fallback_exhaustion_does_not_return_partial_account():
 import requests
 from market_radar_ai.dashboard.account_sync import Reader
 from test_scanner_audit_repairs import Session
 session=Session([requests.ReadTimeout('private'),requests.ReadTimeout('private')])
 reader=Reader('key','secret',session=session,sleep=lambda _:None)
 with pytest.raises(RuntimeError,match='account_read_transport_error'):
  reader('/api/v0/equity/history/orders?limit=50')
 assert len(session.calls)==2 and reader.retries==1
