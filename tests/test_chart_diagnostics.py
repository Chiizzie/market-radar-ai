from test_method_shadow import fixture,NOW
from market_radar_ai.market_data.models import ProviderResult,Candle
from market_radar_ai.market_data.capture import capture_result
from market_radar_ai.market_data.chart_diagnostics import describe

def test_gaps_are_measured_not_filled_or_approved():
    bars=[Candle.model_validate(r) for r in fixture()['candles']];bars.pop(2)
    r=ProviderResult(provider='alpaca_iex',retrieved_at=NOW,candles=bars)
    checked=capture_result(r,now=NOW)['payload'];d=describe(r,checked,now=NOW)
    assert d['category']=='gapped_iex_history' and d['missing_internal_intervals']==1
    assert d['contiguous_tail_bars']==15 and not checked['quality_passed_at_capture']
    assert len(r.candles)==17

def test_empty_success_distinct_from_provider_failure():
    for status,category in [('ok','no_completed_iex_bars'),('error','provider_or_payload_failure')]:
        r=ProviderResult(provider='alpaca_iex',retrieved_at=NOW,status=status)
        assert describe(r,capture_result(r,now=NOW)['payload'],now=NOW)['category']==category

def test_rotation_prefers_fresh_snapshots_but_keeps_exploration():
    from market_radar_ai.market_data.discovery import catalogue_selection
    from datetime import timedelta
    pool=[f'S{i}' for i in range(100)];e={s:{'snapshot_status':'fresh' if i>=50 else 'stale'} for i,s in enumerate(pool)}
    a=catalogue_selection([],pool,NOW,limit=20,evidence=e)
    b=catalogue_selection([],pool,NOW+timedelta(minutes=5),limit=20,evidence=e)
    assert len(a)==len(set(a))==20 and a!=b
    assert sum(e[s]['snapshot_status']=='fresh' for s in a)>=15
    assert any(e[s]['snapshot_status']=='stale' for s in a+b)
