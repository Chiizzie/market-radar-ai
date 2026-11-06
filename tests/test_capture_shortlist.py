from datetime import timedelta
import hashlib
import json
import pytest
from test_market_capture import NOW,result
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.market_data.capture_shortlist import shortlist


def capture(symbols=('XBTEUR','ETHEUR','SOLEUR')):
    def fetch(symbol):
        row=result().candles[0]
        rows=[row.model_copy(update={'symbol':symbol,'timestamp':NOW-timedelta(minutes=5*(20-i)),
              'volume':row.volume}) for i in range(20)]
        return result().model_copy(update={'candles':rows})
    return capture_markets([],symbols,stock_fetch=None,crypto_fetch=fetch,now=NOW)


def test_limits_and_no_admission_or_ai():
    r=shortlist(capture(),now=NOW,crypto_limit=2)
    c=r['markets']['crypto']
    assert c['rankable']==3 and c['shortlisted']==2 and c['deferred_by_limit']==1
    assert r['model_calls']==0 and not r['trade_authorized']
    assert all(x['broker_eligibility']=='UNKNOWN' and x['admission_required'] for x in c['candidates'])


def test_stale_captures_never_rank():
    r=shortlist(capture(),now=NOW+timedelta(hours=1))
    assert r['markets']['crypto']['rankable']==0
    assert len(r['markets']['crypto']['rejected'])==3


def test_tampered_capture_fails():
    d=capture();d['captures'][0]['payload']['provider']='other'
    with pytest.raises(ValueError,match='checksum'):shortlist(d,now=NOW)


def test_insufficient_history_is_explained():
    d=capture(('XBTEUR',));p=d['captures'][0]['payload'];p['candles']=p['candles'][-1:]
    d['captures'][0]['payload_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    r=shortlist(d,now=NOW)
    assert r['markets']['crypto']['rejected'][0]['reason']=='insufficient_history'


@pytest.mark.parametrize('limit',[0,41,True])
def test_invalid_limits(limit):
    with pytest.raises(ValueError):shortlist(capture(),now=NOW,stock_limit=limit)
