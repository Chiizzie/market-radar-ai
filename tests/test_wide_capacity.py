from threading import Lock
from time import sleep,monotonic
import pytest
from test_broader_discovery import bars,NOW,ENV
from market_radar_ai.market_data.providers.alpaca_batch import fetch_histories


def test_1200_symbols_bounded_parallelism_and_one_batch_failure(monkeypatch):
    active=0;peak=0;calls=[];lock=Lock()
    def raw(symbols,**kw):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active);calls.append(tuple(symbols))
        try:
            sleep(.02)
            if 'S500' in symbols:raise ValueError('synthetic outage')
            return {s:bars() for s in symbols}
        finally:
            with lock:active-=1
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.raw_bars',raw)
    r=fetch_histories([f'S{i}' for i in range(1200)],env=ENV,clock=lambda:NOW)
    assert len(calls)==12 and 1<peak<=4 and len(r)==1200
    assert sum(x.status=='ok' for x in r.values())==1100
    assert all(r[f'S{i}'].status=='error' for i in range(500,600))
    assert r['S1199'].candles and r['S0'].candles
    with pytest.raises(ValueError):fetch_histories([f'S{i}' for i in range(1201)],env=ENV,clock=lambda:NOW)
