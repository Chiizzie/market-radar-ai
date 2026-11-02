"""Offline batch boundary: validate supplied evidence before baseline ranking."""
from dataclasses import dataclass
from datetime import datetime
from .admission import Admission, EligibilityEvidence, FxQuote, admit_research
from .models import Instrument, ProviderResult
from .report import ScanReport
from .screener import CandidateScore, rank_candidates


@dataclass(frozen=True)
class ScreeningInput:
    instrument: Instrument
    data: ProviderResult
    eligibility: EligibilityEvidence | None = None
    fx: FxQuote | None = None


@dataclass
class ScreeningResult:
    ranked: list[CandidateScore]
    admissions: dict[str, Admission]
    report: ScanReport


def screen_batch(items: list[ScreeningInput], *, now: datetime,
                 limit: int = 20) -> ScreeningResult:
    if limit < 1:
        raise ValueError('limit must be positive')
    report = ScanReport(discovered=len(items))
    admissions, accepted, candles = {}, [], {}
    counts = {}
    for item in items:
        symbol = item.instrument.symbol
        counts[symbol] = counts.get(symbol, 0) + 1
    for item in items:
        instrument, data = item.instrument, item.data
        symbol = instrument.symbol
        # Existing ranker keys by symbol; reject collisions instead of overwriting.
        if counts[symbol] > 1:
            admission = Admission(accepted=False, failures=('ambiguous_symbol',))
        else:
            admission = admit_research(instrument, data, evidence=item.eligibility,
                                       fx=item.fx, now=now)
        admissions[symbol] = admission
        if data.candles:
            report.fetched += 1
        if data.status != 'ok':
            report.provider_error(data.provider)
        if not admission.accepted:
            report.reject(admission.failures[0])
            continue
        report.quality_passed += 1
        accepted.append(instrument)
        candles[symbol] = data.candles
    ranked = rank_candidates(accepted, candles)[:limit]
    report.shortlisted = len(ranked)
    return ScreeningResult(ranked, admissions, report)
