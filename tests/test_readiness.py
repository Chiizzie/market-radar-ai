from datetime import timedelta
from test_market_capture import NOW, result
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.dashboard.readiness import assess


def test_one_market_is_not_complete_rehearsal():
    doc=capture_markets([],['XBTEUR'],stock_fetch=None,crypto_fetch=lambda _:result(),now=NOW)
    report=assess(doc,now=NOW)
    assert not report['data_rehearsal_passed']
    assert report['checks']['crypto_has_current_data']
    assert not report['trading_ready']


def test_stale_capture_cannot_pass():
    doc=capture_markets([],['XBTEUR'],stock_fetch=None,crypto_fetch=lambda _:result(),now=NOW)
    assert not assess(doc,now=NOW+timedelta(hours=1))['checks']['crypto_has_current_data']
