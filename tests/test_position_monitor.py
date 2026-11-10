from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from market_radar_ai.dashboard.position_monitor import build, episode, notify, linked_plan
from market_radar_ai.market_data.models import Candle, ProviderResult

OPEN=datetime(2026,11,10,16,0,tzinfo=timezone.utc)
NOW=OPEN+timedelta(minutes=30)
def decision():
    return dict(schema_version='paper-final-decision-v1',verdict='PAPER_WATCH_FOR_ENTRY',paper_only=True,
        trade_authorized=False,live_orders_enabled=False,blockers=[],candidate_id='stocks:TEST',packet_id='a'*64,
        evaluated_at=(OPEN-timedelta(seconds=10)).isoformat(),plan=dict(symbol='TEST',currency='EUR',native_currency='USD',
        entry_eur='9',stop_eur='8.1',target_eur='12',quantity='10',assumed_round_trip_cost_eur='1',planned_loss_eur='10',paper_capital_eur='500',fx_rate='0.9',
        expires_at=(OPEN+timedelta(minutes=2)).isoformat(),exit_by=OPEN.replace(hour=20,minute=55).isoformat(),invalidation='Original synthetic condition',trade_authorized=False))
def fill(side='BUY',quantity='10',at=OPEN,price='9.9'):
    return dict(order=dict(ticker='TEST_US_EQ',side=side,currency='USD'),fill=dict(type='TRADE',quantity=quantity,filled_at=at.isoformat(),price_native=price))
def account():
    return dict(account_ref='b'*64,generated_at=NOW.isoformat(),history_complete=True,
        positions=[dict(ticker='TEST_US_EQ',currency='USD',quantity='10')],history=[fill()])
def bars(closes=None):
    closes=closes or [Decimal('10.2')]*21
    rows=[Candle(symbol='TEST',timestamp=NOW-timedelta(minutes=5*(len(closes)-i)),interval='5m',quote_currency='USD',source='alpaca_iex',
        open=str(c),close=str(c),low=str(Decimal(c)-Decimal('.1')),high=str(Decimal(c)+Decimal('.1')),volume='100') for i,c in enumerate(closes)]
    return ProviderResult(provider='alpaca_iex',retrieved_at=NOW,candles=rows)
def run(a=None,d=None,result=None,now=NOW):
    a=a or account();a['generated_at']=now.isoformat()
    return build(a,[d or decision()],now=now,fetch=lambda _: {'TEST':result or bars()})

def test_expired_entry_does_not_remove_actual_holding_or_rewrite_simulation():
    a=account();d=decision();before=deepcopy(d)
    row=run(a,d)['rows'][0]
    assert row['plan']['trigger_native']=='1E+1' and row['state']=='monitoring'
    assert row['entry_native']=='9.9' and d==before

def test_two_completed_closes_fail_breakout_but_one_does_not():
    assert 'failed_breakout' not in run(result=bars([Decimal('10.2')]*20+[Decimal('9.8')]))['rows'][0]['reasons']
    row=run(result=bars([Decimal('10.2')]*19+[Decimal('9.8')]*2))['rows'][0]
    assert row['state']=='review_exit' and 'failed_breakout' in row['reasons'] and 'trend_weakening' in row['reasons']

def test_pre_entry_candles_and_incomplete_candles_cannot_trigger_failure():
    a=account();a['history'][0]['fill']['filled_at']=(NOW-timedelta(minutes=3)).isoformat()
    d=decision();d['plan']['expires_at']=NOW.isoformat()
    assert 'failed_breakout' not in run(a,d,result=bars([Decimal('9.8')]*21))['rows'][0]['reasons']
    result=bars();result.candles.append(result.candles[-1].model_copy(update={'timestamp':NOW}))
    assert run(result=result)['rows'][0]['state']=='data_unavailable'

@pytest.mark.parametrize('fault',['stale','gap','identity','zero_volume'])
def test_bad_market_evidence_never_reports_monitoring(fault):
    result=bars()
    if fault=='stale':result.candles=result.candles[:-2]
    if fault=='gap':result.candles.pop(-2)
    if fault=='identity':result.candles[-1]=result.candles[-1].model_copy(update={'symbol':'WRONG'})
    if fault=='zero_volume':result.candles[-1]=result.candles[-1].model_copy(update={'volume':Decimal(0)})
    assert run(result=result)['rows'][0]['state']=='data_unavailable'

def test_time_cutoff_still_alerts_when_prices_unavailable():
    now=OPEN.replace(hour=20,minute=55)
    row=run(now=now)['rows'][0]
    assert row['state']=='invalidated' and 'exit_due' in row['reasons'] and 'data_unavailable' in row['reasons']
    row=run(now=now-timedelta(minutes=6))['rows'][0]
    assert 'exit_soon' in row['reasons']

def test_recovery_does_not_erase_an_observed_post_entry_stop_close():
    values=[Decimal('10.2')]*21
    values[-3]=Decimal('8.9')
    row=run(result=bars(values))['rows'][0]
    assert row['state']=='invalidated' and 'stop_breached' in row['reasons']

def test_closed_and_unreconciled_positions_never_generate_holding_advice():
    a=account();a['positions']=[];assert run(a)['rows']==[]
    a=account();a['history_complete']=False
    assert run(a)['rows'][0]['plan'] is None
    a=account();a['positions'][0]['quantity']='9'
    assert run(a)['rows'][0]['plan'] is None

def test_partial_sell_and_add_preserve_original_episode_and_average():
    a=account();a['history']+=[fill('SELL','5',OPEN+timedelta(minutes=1)),fill('BUY','5',OPEN+timedelta(minutes=5),'11')]
    result=episode(a,a['positions'][0])
    assert result['opened_at']==OPEN.isoformat() and Decimal(result['entry_native'])==Decimal('10.45')

def test_new_trade_cannot_reuse_old_expired_call_and_later_calls_cannot_replace_original():
    a=account();a['history']+=[fill('SELL','10',OPEN+timedelta(minutes=2)),fill('BUY','10',OPEN+timedelta(minutes=10))]
    assert run(a)['rows'][0]['plan'] is None
    d=decision();d['evaluated_at']=(OPEN+timedelta(seconds=1)).isoformat()
    assert linked_plan([d],'TEST',OPEN.isoformat()) is None

class Ledger:
    def __init__(self):self.keys=set();self.confirmed=set()
    def reserve(self,key):
        if key in self.keys:raise ValueError('delivery_already_attempted_do_not_retry')
        self.keys.add(key)
    def confirm(self,key):self.confirmed.add(key)
class Transport:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def post(self,url,**kw):
        self.calls.append((url,kw))
        if self.fail:raise TimeoutError()
        return type('Response',(),{'status_code':200,'json':lambda _:{'ok':True,'result':{'chat':{'id':123},'message_id':7}}})()
ENV=dict(SEND_POSITION_MONITOR_TELEGRAM='true',REVIEW_INGEST_SECRET='x'*32,TELEGRAM_BOT_TOKEN='test',TELEGRAM_CHAT_ID='123')
def test_notification_dedup_opaque_state_and_uncertain_send_not_retried():
    report=run(result=bars([Decimal('9.8')]*21));ledger=Ledger();transport=Transport(fail=True)
    assert notify(report,account(),env=ENV,ledger=ledger,session=transport)=='unconfirmed'
    assert notify(report,account(),env=ENV,ledger=ledger,session=transport)=='none'
    assert len(transport.calls)==1 and not ledger.confirmed
    assert all(len(k)==73 and 'TEST' not in k for k in ledger.keys)

def test_notification_confirmation_and_price_text():
    ledger=Ledger();transport=Transport();report=run(result=bars([Decimal('9.8')]*21))
    assert notify(report,account(),env=ENV,ledger=ledger,session=transport)=='confirmed'
    text=transport.calls[0][1]['json']['text']
    assert 'No sell order' in text and 'USD' in text and 'failed breakout' in text and ledger.confirmed==ledger.keys
