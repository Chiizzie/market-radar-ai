from datetime import datetime, timezone
from market_radar_ai.market_data.queue import ScanQueue
import pytest

NOW = datetime(2026,11,2,tzinfo=timezone.utc)


def test_rotation_persists_and_markets_have_independent_capacity(tmp_path):
    path = tmp_path/'queue.db'
    q = ScanQueue(path)
    q.replace_universe('stocks',['C','a','A','B'])
    q.replace_universe('crypto',['XBTEUR','ETHEUR'])
    first = q.select(now=NOW,stocks=2,crypto=1)
    assert first['stocks'] == dict(selected=['A','B'],universe_count=3,deferred_count=1)
    second = ScanQueue(path).select(now=NOW,stocks=2,crypto=1)
    assert second['stocks']['selected'][0] == 'C'
    assert second['crypto']['selected'] == ['XBTEUR']


def test_universe_removes_delisted_and_adds_new_symbols(tmp_path):
    q=ScanQueue(tmp_path/'q.db')
    q.replace_universe('stocks',['A','B'])
    q.select(now=NOW,stocks=2,crypto=0)
    q.replace_universe('stocks',['B','C'])
    assert q.select(now=NOW,stocks=1,crypto=0)['stocks']['selected'] == ['C']
    q.replace_universe('stocks',[])
    assert q.select(now=NOW)['stocks']['universe_count'] == 0


def test_invalid_limits_do_not_mutate_queue(tmp_path):
    q=ScanQueue(tmp_path/'q.db')
    with pytest.raises(ValueError): q.select(now=NOW,stocks=-1)
    with pytest.raises(ValueError): q.replace_universe('forex',['EURUSD'])
