from copy import deepcopy
from datetime import datetime, timedelta, timezone
from market_radar_ai.agents.early_screening import screen
from market_radar_ai.agents.candidate_packages import digest
from test_stock_context import document, NOW


def test_premarket_does_not_need_twenty_bars():
    result=screen(document(),now=NOW)
    assert result['candidates'][0]['state']=='PREMARKET_RESEARCH'
    assert result['model_calls']==0 and not result['trade_authorized']


def opening_document():
    doc=document();p=doc['stock_context'][0]['payload']
    opening=datetime(2026,11,4,14,30,tzinfo=timezone.utc)
    now=opening+timedelta(minutes=20)
    original=p['intraday']['bars'][0]
    p['intraday']['bars']=[{**original,'timestamp':(opening+timedelta(minutes=5*i)).isoformat()} for i in range(4)]
    p['retrieved_at']=now.isoformat()
    doc['stock_context'][0]['payload_sha256']=digest(p)
    return doc,now


def test_first_fifteen_minutes_measured_before_twenty_bars():
    doc,now=opening_document()
    row=screen(doc,now=now)['candidates'][0]
    assert row['regular_bars_available']==4
    assert row['opening_range_state']=='INSIDE_RANGE'
    assert row['opening_range_high_native']=='102'


def test_missing_first_bar_never_fakes_opening_range():
    doc,now=opening_document();p=doc['stock_context'][0]['payload']
    p['intraday']['bars'].pop(0);doc['stock_context'][0]['payload_sha256']=digest(p)
    assert screen(doc,now=now)['candidates'][0]['opening_range_state']=='WAITING_FOR_COMPLETE_FIRST_15_MINUTES'


def test_tamper_stale_and_future_fail_closed():
    doc,now=opening_document()
    assert screen(doc,now=now+timedelta(minutes=16))['candidates'][0]['state']=='UNAVAILABLE'
    doc['stock_context'][0]['payload']['symbol']='OTHER'
    assert screen(doc,now=now)['candidates'][0]['state']=='UNAVAILABLE'
    doc,now=opening_document()
    assert screen(doc,now=now-timedelta(seconds=1))['candidates'][0]['state']=='UNAVAILABLE'
