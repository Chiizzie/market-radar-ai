from datetime import timedelta
from decimal import Decimal
from itertools import product
import json

import pytest
from test_broader_discovery import NOW, ENV, Session
from test_discovery import Session as ActivitySession
from market_radar_ai.market_data.discovery import discover
from market_radar_ai.market_data.discovery_signals import load_checkpoint, save_checkpoint, measurements
from market_radar_ai.market_data.providers.alpaca_batch import discover_snapshots


def snapshot(price=100, volume=100000000, previous_volume=500000000):
    return {'latestTrade': {'p': price, 't': NOW.isoformat()},
            'dailyBar': {'v': volume, 't': NOW.replace(hour=5).isoformat()},
            'prevDailyBar': {'c': price, 'v': previous_volume,
                            't': (NOW-timedelta(days=1)).replace(hour=5).isoformat()}}


def test_relative_participation_and_recent_move_can_beat_absolute_turnover():
    data = {'MEGA': snapshot(), 'SMALL': snapshot(77.78, 1638788, 1000000)}
    prior = {'SMALL': {'price': '77.37', 'observed_at': (NOW-timedelta(minutes=5)).isoformat()}}
    r = discover_snapshots(list(data), env=ENV, now=NOW, prior_snapshots=prior,
                          session=Session(lambda *a: data), clock=lambda: NOW)
    assert r['ranked_symbols'][0] == 'SMALL'
    e = r['symbol_evidence']['SMALL']
    assert 0.52 < e['acceleration_pct'] < 0.54
    assert e['relative_session_volume'] > 1.6
    assert e['turnover_usd'] < r['symbol_evidence']['MEGA']['turnover_usd']
    assert 'not_same_time' in r['relative_volume_basis']


@pytest.mark.parametrize('fault', ['missing', 'zero', 'future', 'stale', 'previous_session', 'unchanged_stamp', 'nan'])
def test_missing_or_invalid_acceleration_is_unknown_not_a_surge(fault):
    prior = {'price': '10', 'observed_at': (NOW-timedelta(minutes=5)).isoformat()}
    if fault == 'missing': prior = None
    elif fault == 'zero': prior['price'] = '0'
    elif fault == 'future': prior['observed_at'] = (NOW+timedelta(seconds=1)).isoformat()
    elif fault == 'stale': prior['observed_at'] = (NOW-timedelta(minutes=31)).isoformat()
    elif fault == 'previous_session': prior['observed_at'] = (NOW-timedelta(days=1)).isoformat()
    elif fault == 'unchanged_stamp': prior['observed_at'] = NOW.isoformat()
    elif fault == 'nan': prior['price'] = 'NaN'
    r = measurements(Decimal(11), Decimal(100), Decimal(10), None, at=NOW, prior=prior)
    assert r['acceleration_pct'] is None and r['relative_session_volume'] is None


def test_checkpoint_preserves_observation_time_and_rejects_corruption_and_old_sessions(tmp_path):
    path = tmp_path/'snapshots.json'
    assert load_checkpoint(path, now=NOW) == ({}, 'cold_start')
    values = {'SMALL': {'price': '77.37', 'observed_at': (NOW-timedelta(minutes=5)).isoformat()}}
    assert save_checkpoint(path, values, now=NOW) == 'saved'
    assert load_checkpoint(path, now=NOW+timedelta(minutes=5)) == (values, 'reused')
    for at in [NOW-timedelta(seconds=1), NOW+timedelta(minutes=31), NOW+timedelta(days=1)]:
        assert load_checkpoint(path, now=at)[0] == {}
    body = json.loads(path.read_text()); body['payload']['snapshots']['SMALL']['price'] = '1'
    path.write_text(json.dumps(body))
    assert load_checkpoint(path, now=NOW)[0] == {}


def test_each_snapshot_has_an_explicit_freshness_or_failure_reason():
    data = {s: snapshot() for s in ['GOOD','OLD','BAD']}
    data['OLD']['latestTrade']['t'] = (NOW-timedelta(hours=1)).isoformat()
    data['BAD']['latestTrade']['p'] = 'NaN'
    r = discover_snapshots([*data, 'MISSING'], env=ENV, now=NOW,
                          session=Session(lambda *a:data), clock=lambda:NOW)
    assert r['ranked_symbols'] == ['GOOD']
    assert {s:e['snapshot_status'] for s,e in r['symbol_evidence'].items()} == {
        'GOOD':'fresh', 'OLD':'stale_or_wrong_session', 'BAD':'invalid_snapshot', 'MISSING':'not_received'}


def test_relative_lead_reaches_research_and_every_deferred_symbol_is_traceable(monkeypatch, tmp_path):
    pool = ['M'+''.join(x) for x in product('ABCDEFGHIJKLMNOPQRSTUVWXYZ', repeat=3)][:1000]+['SMALL']
    monkeypatch.setattr('market_radar_ai.market_data.discovery_universe.load_universe',
                        lambda **k: {'symbols': pool, 'failures': []})
    def reply(url, params):
        return {s: snapshot(77.78, 1638788, 1000000) if s=='SMALL' else snapshot()
                for s in params['symbols'].split(',')}
    def snapshots(symbols, **kwargs):
        return discover_snapshots(symbols, **kwargs, session=Session(reply), clock=lambda:NOW)
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.discover_snapshots', snapshots)
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.fetch_histories',
                        lambda symbols, **k: {s:s for s in symbols})
    monkeypatch.setattr('market_radar_ai.market_data.capture.capture_result',
                        lambda *a, **k: {'payload': {'quality_passed_at_capture': True}})
    r = discover(env={**ENV,'ENABLE_BROAD_DISCOVERY':'true','SCREEN_DISCOVERY_DATA':'true'},
                 now=NOW, fallback=['MU'], session=ActivitySession(stamp=NOW.isoformat()),
                 universe_cache_path=tmp_path/'universe.json')
    manifest = {s['symbol']:s for s in r['selection_manifest']}
    assert set(manifest) == set(pool)
    assert r['screening']['checked'] == 1001 and len(r['selected_symbols']) == 79
    assert manifest['SMALL']['screen_lane'] == 'priority'
    assert manifest['SMALL']['detail_selected'] and 'SMALL' in r['selected_symbols']
    assert sum(s['selection_reason']=='outside_technical_budget' for s in manifest.values()) == 0
    assert sum(s['selection_reason']=='outside_detail_budget' for s in manifest.values()) == 922
    assert r['snapshot_coverage']['checkpoint_save'] == 'saved'
    assert 'checkpoint' not in r['snapshot_coverage']
