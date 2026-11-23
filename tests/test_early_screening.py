from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from market_radar_ai.agents.early_screening import screen
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.market_data.capture import capture_result
from market_radar_ai.market_data.models import ProviderResult
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


def afternoon_document():
    doc, _ = opening_document()
    context = doc['stock_context'][0]
    p = context['payload']
    opening = datetime(2026, 11, 23, 14, 30, tzinfo=timezone.utc)
    now = opening + timedelta(minutes=251)
    original = p['intraday']['bars'][0]
    bars = [{**original, 'timestamp': (opening + timedelta(minutes=5*i)).isoformat()}
            for i in range(50)]
    bars[1].update(high='108', low='95')
    p['intraday']['bars'] = bars[-24:]
    p['retrieved_at'] = now.isoformat()
    context['payload_sha256'] = digest(p)
    provider = ProviderResult(provider='alpaca_iex', retrieved_at=now, candles=bars)
    chart = capture_result(provider, now=now)
    doc['captures'] = [{**chart, 'market': 'stocks', 'requested_symbol': original['symbol']}]
    return doc, now


def test_rolling_context_recovers_only_the_actual_opening_from_the_same_capture():
    doc, now = afternoon_document()
    original = deepcopy(doc)
    row = screen(doc, now=now)['candidates'][0]
    assert row['regular_bars_available'] == 24
    assert (row['opening_range_low_native'], row['opening_range_high_native']) == ('95', '108')
    assert row['opening_range_state'] == 'INSIDE_RANGE' and not row['trade_authorized']
    assert doc == original


@pytest.mark.parametrize('fault', ['tamper', 'bad_quality', 'wrong_symbol', 'wrong_source', 'nonfinite',
                                   'missing_open', 'different_latest', 'future', 'duplicate', 'bad_list', 'bad_row'])
def test_unusable_alternate_chart_does_not_invent_an_opening_range(fault):
    doc, now = afternoon_document()
    row = doc['captures'][0]
    p = row['payload']
    if fault == 'bad_quality': p['quality_passed_at_capture'] = False
    if fault == 'wrong_symbol': p['candles'][0]['symbol'] = 'OTHER'
    if fault == 'wrong_source': p['candles'][0]['source'] = 'alpaca_sip_delayed'
    if fault == 'nonfinite': p['candles'][0]['high'] = 'Infinity'
    if fault == 'missing_open': p['candles'].pop(0)
    if fault == 'different_latest': p['candles'][-1]['volume'] = '99'
    if fault == 'future': p['captured_at_dublin'] = (now + timedelta(seconds=1)).isoformat()
    if fault == 'duplicate': doc['captures'].append(deepcopy(row))
    if fault == 'bad_list': doc['captures'] = None
    if fault == 'bad_row': doc['captures'].append(None)
    row['payload_sha256'] = 'bad' if fault == 'tamper' else digest(p)
    result = screen(doc, now=now)['candidates'][0]
    assert result['opening_range_state'] == 'WAITING_FOR_COMPLETE_FIRST_15_MINUTES'
    assert 'opening_range_high_native' not in result and 'opening_range_low_native' not in result


def test_tamper_stale_and_future_fail_closed():
    doc,now=opening_document()
    assert screen(doc,now=now+timedelta(minutes=16))['candidates'][0]['state']=='UNAVAILABLE'
    doc['stock_context'][0]['payload']['symbol']='OTHER'
    assert screen(doc,now=now)['candidates'][0]['state']=='UNAVAILABLE'
    doc,now=opening_document()
    assert screen(doc,now=now-timedelta(seconds=1))['candidates'][0]['state']=='UNAVAILABLE'
