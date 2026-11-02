from datetime import datetime, timedelta, timezone
from decimal import Decimal
from market_radar_ai.market_data.models import Candle, Instrument
from market_radar_ai.market_data.screener import rank_candidates

def test_ranker_scores_positive_momentum():
    instrument = Instrument(symbol="ABC", asset_class="equity", quote_currency="USD", venue="test")
    start = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(25):
        close = Decimal(str(100+i))
        rows.append(Candle(symbol="ABC", interval="5m", timestamp=start+timedelta(minutes=5*i),
            open=close, high=close+1, low=close-1, close=close, volume=Decimal("1000"),
            quote_currency="USD", source="test"))
    ranked = rank_candidates([instrument], {"ABC": rows})
    assert len(ranked) == 1 and ranked[0].score > 0
