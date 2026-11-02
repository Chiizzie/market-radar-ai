"""Validated data-to-team handoff. The earlier unrestricted stub is retired."""
from datetime import datetime
from .agents.paper_team import PaperTeam, ResearchInput
from .market_data.admission import admit_research
from .market_data.screening import ScreeningInput

# One orchestration implementation; arbitrary/paid adapters cannot bypass gates.
AnalysisPipeline = PaperTeam


def prepare_research(item: ScreeningInput, *, candidate_id: str, now: datetime,
                     facts=(), missing_data=()) -> ResearchInput:
    admission = admit_research(item.instrument, item.data, evidence=item.eligibility,
                               fx=item.fx, now=now)
    if not admission.accepted:
        raise ValueError('Research admission rejected: ' + ', '.join(admission.failures))
    latest = max(item.data.candles, key=lambda c: c.timestamp)
    evidence = item.eligibility
    sources = tuple(dict.fromkeys([item.data.provider, latest.source, evidence.source,
                                   admission.fx_source]))
    return ResearchInput(candidate_id=candidate_id, symbol=item.instrument.symbol,
        observed_at=latest.timestamp, asset_class=item.instrument.asset_class,
        broker=evidence.broker, broker_verified_until=evidence.expires_at,
        quality_passed=True, source_ids=sources,
        facts=(f'Latest native close: {admission.native_close} {item.instrument.quote_currency}',
               f'Latest indicative EUR close: {admission.eur_close}') + tuple(facts),
        missing_data=tuple(missing_data))
