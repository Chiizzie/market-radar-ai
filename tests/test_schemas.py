from datetime import datetime, timezone
import pytest
from market_radar_ai.schemas import CandidateSnapshot

def test_candidate_snapshot_is_immutable():
    candidate = CandidateSnapshot(
        candidate_id="test-1", symbol="TEST", asset_class="equity",
        observed_at=datetime.now(timezone.utc), currency="EUR", last_price=10,
        source_ids=["test-feed"], data_quality_passed=True
    )
    with pytest.raises(Exception):
        candidate.symbol = "OTHER"
