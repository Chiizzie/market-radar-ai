from copy import deepcopy
from datetime import timedelta
import json
import pytest
from test_capture_shortlist import capture, NOW
from market_radar_ai.dashboard.export import build_snapshot
from market_radar_ai.agents.candidate_packages import digest


def test_real_capture_candles_export_without_trade_annotations():
    d=capture(('XRPEUR',));s=build_snapshot(d,now=NOW)
    chart=s['charts']['series'][0]
    assert chart['symbol']=='XRPEUR' and chart['quote_currency']=='EUR' and chart['fx'] is None
    assert chart['capture_sha256']==d['captures'][0]['payload_sha256']
    assert len(chart['candles'])==20 and set(chart['candles'][0])=={'timestamp','open','high','low','close','volume'}
    assert s['markets']['crypto'][0]['decision']=='NO_ACTION' and s['agents']['reports']==[]
    assert 'entry' not in chart and not s['live_orders_enabled']


def test_stale_or_tampered_capture_never_exports_chart():
    d=capture(('XRPEUR',))
    assert build_snapshot(d,now=NOW+timedelta(minutes=20))['charts']['series']==[]
    d['captures'][0]['payload']['candles'][0]['close']='1'
    with pytest.raises(ValueError,match='checksum'):build_snapshot(d,now=NOW)


@pytest.mark.parametrize('fault',['valid','expired','future','hash','currency'])
def test_eur_conversion_requires_current_hash_checked_fx(fault):
    d=capture(('TEST',));c=d['captures'][0]
    for row in c['payload']['candles']:row['quote_currency']='USD'
    c['payload_sha256']=digest(c['payload'])
    fx={'native_currency':'USD','eur_per_unit':'0.9','source':'synthetic','observed_at':NOW.isoformat()}
    if fault=='expired':fx['observed_at']=(NOW-timedelta(minutes=15)).isoformat()
    if fault=='future':fx['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='currency':fx['native_currency']='GBP'
    p={'fx':fx};d['stock_reference_checks']={'payload':p,'payload_sha256':digest(p) if fault!='hash' else 'bad'}
    chart=build_snapshot(d,now=NOW)['charts']['series'][0]
    assert chart['candles'][0]['close']=='100' # native evidence is unchanged
    assert (chart['fx'] is not None)==(fault=='valid')


def test_chart_payload_under_ingestion_limit_for_twenty_four_series():
    doc=capture(('XRPEUR',));original=doc['captures'][0];doc['captures']=[]
    for i in range(24):
        c=deepcopy(original);c['requested_symbol']='S'+str(i)
        for row in c['payload']['candles']:row['symbol']=c['requested_symbol']
        c['payload_sha256']=digest(c['payload']);doc['captures'].append(c)
    doc['coverage']['crypto'].update(requested=24,attempted=24,successful=24,quality_passed=24,deferred=[])
    s=build_snapshot(doc,now=NOW)
    assert len(s['charts']['series'])==24 and len(json.dumps(s).encode())<2*1024*1024
