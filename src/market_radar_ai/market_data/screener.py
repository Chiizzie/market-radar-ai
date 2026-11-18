from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from .models import Candle, Instrument

@dataclass(frozen=True)
class CandidateScore:
    symbol: str
    asset_class: str
    score: float
    reasons: tuple[str, ...]

def rank_candidates(instruments: Iterable[Instrument], candles_by_symbol: dict[str, list[Candle]], *, min_candles: int = 20) -> list[CandidateScore]:
    """Transparent baseline momentum/participation ranker, not a trade recommendation."""
    ranked = []
    for instrument in instruments:
        candles = sorted(candles_by_symbol.get(instrument.symbol, []), key=lambda c: c.timestamp)
        if len(candles) < min_candles: continue
        closes, volumes = [float(c.close) for c in candles], [float(c.volume) for c in candles]
        if closes[-min_candles] <= 0: continue
        momentum = (closes[-1] / closes[-min_candles] - 1.0) * 100.0
        recent_n = min(5, min_candles//2)
        recent = sum(volumes[-recent_n:]) / recent_n
        baseline = sum(volumes[-min_candles:-recent_n]) / max(min_candles - recent_n, 1)
        relative_volume = recent / baseline if baseline > 0 else 0.0
        score = max(-10.0, min(10.0, momentum)) + min(relative_volume, 5.0)
        reasons = [f"{momentum:.2f}% change across {min_candles} candles"]
        if relative_volume >= 1.5: reasons.append(f"{relative_volume:.2f}x recent relative volume")
        ranked.append(CandidateScore(instrument.symbol, instrument.asset_class, round(score, 3), tuple(reasons)))
    return sorted(ranked, key=lambda item: item.score, reverse=True)
