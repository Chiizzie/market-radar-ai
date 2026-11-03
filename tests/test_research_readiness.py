from datetime import timedelta
import pytest
from test_evidence_enrichment import reference, news
from test_capture_shortlist import capture, NOW
from market_radar_ai.market_data.readiness import readiness


def test_current_crypto_research_and_expiry_replays_do_not_authorize():
    d = capture(('XRPEUR',)); d['reference_quote_capture'] = reference()
    r = readiness(d, news(), now=NOW)
    assert r['reference_quotes']['status'] == 'current_reference_only'
    assert r['candidates'][0]['research_ready_at_check'] is True
    assert r['candidates'][0]['trade_ready'] is False
    assert r['candidates'][0]['expiry_replay']['rejected'] is True
    assert r['capture_expiry_replay']['all_original_captures_rejected'] is True
    assert not r['trade_authorized'] and r['model_calls'] == r['orders_submitted'] == 0
    assert r['stock_warmup']['current_session_minutes_required'] == 100


@pytest.mark.parametrize('hour', [22, 23])
def test_after_cutoff_is_explicit_even_with_no_fresh_candidates(hour):
    r = readiness(capture(), None, now=NOW.replace(hour=hour))
    assert r['mode'] == 'AFTER_CUTOFF_RESEARCH_ONLY' and not r['entry_window_open']
    assert not r['candidates'] and not r['trade_authorized']


def test_stale_reference_cannot_hide_behind_fresh_candles():
    d = capture(('XRPEUR',)); d['reference_quote_capture'] = reference()
    r = readiness(d, news(), now=NOW+timedelta(seconds=31))
    assert r['reference_quotes']['status'] == 'unavailable_invalid_or_stale'
    assert 'reference_quote_unavailable_or_stale' in r['candidates'][0]['missing_evidence']


def test_tampered_captures_fail_report():
    d = capture();d['captures'][0]['payload']['candles'][0]['close'] = '1'
    with pytest.raises(ValueError, match='checksum'):
        readiness(d, None, now=NOW)
