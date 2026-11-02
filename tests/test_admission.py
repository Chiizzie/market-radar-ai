from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from market_radar_ai.market_data.admission import EligibilityEvidence, FxQuote, admit_research
from market_radar_ai.market_data.models import Instrument, Candle, ProviderResult

NOW = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)


def inputs():
    instrument = Instrument(symbol='ABC', provider_symbol='ABC', asset_class='equity', quote_currency='USD', venue='NASDAQ')
    evidence = EligibilityEvidence(broker='trading212_invest', asset_class='equity', provider_symbol='ABC', venue='NASDAQ', broker_instrument_id='ABC_US_EQ', source='test catalogue fixture', verified_at=NOW-timedelta(hours=1), expires_at=NOW+timedelta(hours=1), eligible=True)
    fx = FxQuote(native_currency='USD', eur_per_unit=Decimal('0.9'), observed_at=NOW, source='test FX fixture')
    rows = [Candle(symbol='ABC', interval='5m', timestamp=NOW-timedelta(minutes=5*i), open=100, high=101, low=99, close=100, volume=10, quote_currency='USD', source='fixture') for i in range(20, 0, -1)]
    data = ProviderResult(provider='fixture', retrieved_at=NOW, candles=rows)
    return instrument, data, dict(evidence=evidence, fx=fx, now=NOW)


def test_converts_with_native_price_and_provenance():
    i, d, args = inputs()
    result = admit_research(i, d, **args)
    assert result.accepted and result.eur_close == Decimal('90')
    assert result.native_close == 100 and result.fx_source == 'test FX fixture'


@pytest.mark.parametrize('change,reason', [
    ('missing_broker', 'broker_unverified'), ('expired', 'broker_evidence_invalid'),
    ('wrong_venue', 'broker_evidence_invalid'), ('wrong_broker', 'broker_evidence_invalid'),
    ('stale_fx', 'fx_unavailable_or_stale'), ('future_fx', 'fx_unavailable_or_stale'),
    ('missing_fx', 'fx_unavailable_or_stale'), ('partial', 'provider_not_clean'),
    ('stale_candles', 'stale_candle'), ('forming', 'incomplete_candle'),
    ('wrong_currency', 'candle_identity_mismatch'), ('empty', 'empty_candles'),
])
def test_fail_closed(change, reason):
    i, d, args = inputs()
    if change == 'missing_broker': args['evidence'] = None
    elif change == 'expired': args['evidence'] = args['evidence'].model_copy(update={'expires_at': NOW})
    elif change == 'wrong_venue': args['evidence'] = args['evidence'].model_copy(update={'venue': 'OTHER'})
    elif change == 'wrong_broker': args['evidence'] = args['evidence'].model_copy(update={'broker': 'robinhood_europe'})
    elif change in ('stale_fx', 'future_fx'):
        args['fx'] = args['fx'].model_copy(update={'observed_at': NOW + timedelta(hours=-1 if change == 'stale_fx' else 1)})
    elif change == 'missing_fx': args['fx'] = None
    elif change == 'partial': d.status = 'partial'
    elif change == 'stale_candles': args['now'] = NOW + timedelta(minutes=30)
    elif change == 'forming': d.candles[-1] = d.candles[-1].model_copy(update={'timestamp': NOW})
    elif change == 'wrong_currency': d.candles[-1] = d.candles[-1].model_copy(update={'quote_currency': 'GBP'})
    elif change == 'empty': d.candles = []
    result = admit_research(i, d, **args)
    assert not result.accepted and reason in result.failures
    assert result.eur_close is None


@pytest.mark.parametrize('rate', ['NaN', 'Infinity', '0', '-1'])
def test_invalid_fx_rejected(rate):
    with pytest.raises(ValidationError):
        FxQuote(native_currency='USD', eur_per_unit=rate, observed_at=NOW, source='fixture')


def test_native_eur_needs_no_fx():
    i, d, args = inputs()
    i = i.model_copy(update={'quote_currency': 'EUR'})
    d.candles = [c.model_copy(update={'quote_currency': 'EUR'}) for c in d.candles]
    args['fx'] = None
    assert admit_research(i, d, **args).eur_close == 100


def test_batch_filters_before_ranking_and_accounts_for_rejections():
    from market_radar_ai.market_data.screening import ScreeningInput, screen_batch
    i, d, args = inputs()
    result = screen_batch([ScreeningInput(i, d, args['evidence'], args['fx'])], now=NOW)
    assert len(result.ranked) == 1 and result.report.quality_passed == 1
    blocked = screen_batch([ScreeningInput(i, d)], now=NOW)
    assert not blocked.ranked and blocked.report.rejected == {'broker_unverified': 1}


def test_symbol_collisions_never_overwrite_identity():
    from market_radar_ai.market_data.screening import ScreeningInput, screen_batch
    i, d, args = inputs()
    item = ScreeningInput(i, d, args['evidence'], args['fx'])
    result = screen_batch([item, item], now=NOW)
    assert not result.ranked and result.report.rejected == {'ambiguous_symbol': 2}


def test_valid_data_handoff_reaches_six_role_team():
    from market_radar_ai.pipeline import prepare_research, AnalysisPipeline
    from market_radar_ai.market_data.screening import ScreeningInput
    from market_radar_ai.agents.paper_team import SimulatedAgent, PaperPlan
    from market_radar_ai.agents.roles import AgentRole
    i, d, args = inputs()
    candidate = prepare_research(ScreeningInput(i, d, args['evidence'], args['fx']), candidate_id='integration', now=NOW)
    team = AnalysisPipeline([SimulatedAgent(role, stance='support', source='fixture') for role in AgentRole])
    result = team.run(candidate, now=NOW, plan=PaperPlan(entry=90, stop=89, target=92, quantity=10, costs_eur=1, invalidation='fixture', exit_by=NOW.replace(hour=22)))
    assert result.verdict == 'PAPER_PLAN' and len(result.reports) == 6
