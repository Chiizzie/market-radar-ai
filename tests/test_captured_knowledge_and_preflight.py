"""Synthetic clocks and saved packet integrity; no provider/model/notification calls."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest

from test_pullback_strategy import synthetic_setup, empty_feed
from test_knowledge_retrieval import library
from market_radar_ai.agents.candidate_packages import canonical, digest
from market_radar_ai.agents.knowledge_shadow import prepare, prepare_captured
from market_radar_ai.agents.knowledge_pair import validate_pair, run_pair
from market_radar_ai.agents.manual_plan_preflight import assess_packets
from market_radar_ai.agents.paper_comparison import aware
from market_radar_ai.agents.paper_verdict import build_packets
from market_radar_ai.agents.execution_research import size


def capture():
    doc, _, old = synthetic_setup()
    delta = timedelta(days=16-old.day)
    def shift(value):
        if isinstance(value, dict):
            result = {k:shift(v) for k,v in value.items()}
            if 'payload_sha256' in result and 'payload' in result:
                result['payload_sha256'] = digest(result['payload'])
            return result
        if isinstance(value, list):
            return [shift(v) for v in value]
        if isinstance(value, str) and value.startswith('2026-') and 'T' in value:
            return (aware(value)+delta).isoformat()
        return value
    doc, now = shift(doc), old+delta
    feed = empty_feed('TEST', now)
    packets = build_packets(doc, feed, now=now)
    assert len(packets['packets']) == 1
    return doc, feed, packets, now


def test_late_preparation_retains_exact_original_inputs_without_backdating():
    doc, feed, packets, source = capture()
    before = canonical((doc,feed,packets))
    later = source+timedelta(minutes=5)
    assert prepare(doc,feed,library(),now=later)['paired_inputs'] == 0
    result = prepare_captured(doc,feed,library(),packets,now=later)
    assert result['paired_inputs'] == 1 and result['source_age_seconds'] == 300
    assert result['as_of'] == later.isoformat() and not result['live_review_ready']
    pair = result['pairs'][0]
    assert pair['prepared_at'] == later.isoformat()
    assert pair['source_qualified_at'] == source.isoformat()
    assert pair['packet'] == packets['packets'][0]
    assert canonical((doc,feed,packets)) == before
    assert result['model_calls'] == 0 and not result['trade_authorized']


@pytest.mark.parametrize('fault', ['future','packet_hash','rehashed_plan','missing_packet','changed_capture','scope'])
def test_unbound_or_modified_capture_fails_closed(fault):
    doc,feed,packets,source=capture()
    if fault=='future':source-=timedelta(seconds=1)
    elif fault=='packet_hash':packets['packets'][0]['packet_id']='a'*64
    elif fault=='rehashed_plan':
        p=packets['packets'][0];p['packet']['plan']['target_eur']='999'
        p['packet_id']=digest(p['packet'])
    elif fault=='missing_packet':packets['packets']=[]
    elif fault=='scope':packets['trade_authorized']=True
    else:doc['stock_reference_checks']['payload']['quotes']['quotes']['TEST']['ap']=999
    with pytest.raises(ValueError):prepare_captured(doc,feed,library(),packets,now=source)


def test_saved_preparation_cannot_enter_paid_adapter_even_while_originally_fresh():
    doc,feed,packets,source=capture();lib=library()
    pair=prepare_captured(doc,feed,lib,packets,now=source)['pairs'][0]
    with pytest.raises(ValueError,match='fresh_preparation'):
        validate_pair(pair,lib,now=source)
    with pytest.raises(ValueError,match='fresh_preparation'):
        run_pair(pair,lib,ask=lambda *a:pytest.fail('No paid call'),clock=lambda:source)
    pair.pop('input_use')
    with pytest.raises(ValueError):validate_pair(pair,lib,now=source)


def test_library_not_available_at_original_capture_cannot_leak_future_knowledge():
    doc,feed,packets,source=capture();lib=library()
    lib['built_at']=(source+timedelta(seconds=1)).isoformat()
    lib['library_id']=digest({k:v for k,v in lib.items() if k!='library_id'})
    with pytest.raises(ValueError,match='not_available'):
        prepare_captured(doc,feed,lib,packets,now=source+timedelta(days=1))


def test_cost_preflight_reuses_frozen_math_and_does_not_claim_notification_or_fill():
    _,_,captured,source=capture();packets=captured['packets'];original=deepcopy(packets)
    result=assess_packets(packets,source_at=source,processed_at=source+timedelta(minutes=5))
    expected=size('eur_conversion',packets[0]['packet']['plan']);row=result['rows'][0]
    assert Decimal(row['estimated_net_rr']) == expected['rr']
    assert Decimal(row['quantity']) <= Decimal(packets[0]['packet']['plan']['quantity'])
    assert Decimal(row['estimated_risk_eur']) <= 20 and Decimal(row['estimated_capital_eur']) <= 500
    assert row['notification_acknowledged_at'] is None
    assert row['response_eligibility']=='unknown_without_notification_and_fresh_quote'
    assert not result['costs_verified'] and not result['ordinary_alerts_changed']
    assert not result['trade_authorized'] and packets==original


def test_cost_failures_remain_visible_and_no_target_is_inflated():
    _,_,captured,source=capture();p=captured['packets'][0]
    # Original candidate remains code-qualified; itemised costs can still reject it.
    original = deepcopy(p)
    from market_radar_ai.agents.paper_comparison import validate_packet
    validate_packet(p,source)
    report=assess_packets([p],source_at=source,processed_at=source)
    assert Decimal(report['rows'][0]['estimated_net_rr']) < 2
    assert report['cost_reason_counts']=={'scenario_net_reward_below_2r':1}
    assert report['cost_status_counts']=={'blocked_under_assumptions':1}
    assert p == original


def test_duplicate_and_future_source_are_rejected():
    _,_,captured,source=capture();p=captured['packets']
    with pytest.raises(ValueError):assess_packets(p*2,source_at=source,processed_at=source)
    with pytest.raises(ValueError):assess_packets(p,source_at=source,processed_at=source-timedelta(seconds=1))
