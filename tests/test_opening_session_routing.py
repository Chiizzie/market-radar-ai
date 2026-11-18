from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from unittest.mock import Mock

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.dashboard.collection_notification import notify
from market_radar_ai.dashboard.opening_brief import build, lines, waiting_for_opening_update
from market_radar_ai.market_data.coverage_lanes import select_details
from market_radar_ai.market_data.discovery import technical_priority
from market_radar_ai.market_data.models import ProviderResult
from market_radar_ai.market_data.opening_discovery import chart_priority, phase, prior_news
from test_collection_notification import ENV
from test_opening_improvements import early_input


def test_early_chart_can_take_existing_technical_slot_without_borrowing_bars():
    inputs, now = early_input()
    chart = ProviderResult(provider='alpaca_iex', retrieved_at=now, candles=inputs['candles'])
    assert technical_priority(chart) == (False, 0)
    assert chart_priority(chart, 'TEST', phase(now), technical_priority(chart)) > 0
    assert chart_priority(chart, 'OTHER', phase(now), (False, 0)) is None
    assert chart_priority(chart.model_copy(update={'candles': chart.candles[1:]}), 'TEST', phase(now), (False, 0)) is None
    for minutes in (-5, 5, 15):
        later = chart.model_copy(update={'retrieved_at': now + timedelta(minutes=minutes)})
        assert chart_priority(later, 'TEST', phase(later.retrieved_at), (False, 0)) is None
    pool = ['NVDA', 'AMD'] + [f'X{i}' for i in range(80)] + ['TEST']
    before, _ = select_details(pool, ['X0'], now, 18, ['X1'])
    after, lanes = select_details(pool, ['X0'], now, 18, ['X1'], opening_priority=['TEST'], opening_lane=phase(now))
    assert len(before) == len(set(after)) == 18 and lanes['TEST'] == 'opening_range'
    assert lanes['NVDA'] == 'liquid_core' and lanes['X0'] == 'sector_mover' and lanes['X1'] == 'related_company_catalyst'
    assert sum(v in ('opening_range', 'technical_leader') for v in lanes.values()) == 10
    assert sum(v == 'rotation' for v in lanes.values()) == 4


def test_30m_priority_requires_untriggered_chart_and_latest_completed_bar():
    inputs, opening_15 = early_input()
    now = opening_15 + timedelta(minutes=15)
    bars = inputs['candles']
    start = datetime.fromisoformat(bars[0]['timestamp'])
    for i in range(3, 6):
        bars.append({**bars[-1], 'timestamp': (start + timedelta(minutes=i*5)).isoformat(), 'volume': '300000'})
    result = ProviderResult(provider='alpaca_iex', retrieved_at=now, candles=bars)
    assert technical_priority(result)[0] and chart_priority(result, 'TEST', phase(now), technical_priority(result)) is not None
    other = result.model_copy(update={'retrieved_at': now + timedelta(minutes=5)})
    assert chart_priority(other, 'TEST', phase(now), (True, 5)) is None
    bars[-1].update(close='105', high='105')
    crossed = ProviderResult(provider='alpaca_iex', retrieved_at=now, candles=bars)
    assert chart_priority(crossed, 'TEST', phase(now), (True, 5)) is None


def test_news_hint_preserves_publication_receipt_and_cache_clocks(tmp_path):
    at = datetime(2026, 11, 18, 15, tzinfo=UTC)
    item = {'kind': 'news', 'title': 'Issuer release', 'source': 'wire', 'url': 'https://example.com/issuer',
            'published_at': (at-timedelta(minutes=25)).isoformat(), 'retrieved_at': at.isoformat(), 'symbols': ['TEST']}
    feed = {'status': 'partial', 'retrieved_at': at.isoformat(), 'items': [item]}
    path = tmp_path / 'cache.json'
    body = {'version': 1, 'collection_started_at': at.isoformat(), 'news': feed}
    def write():
        path.write_text(json.dumps({'payload': body, 'sha256': digest(body)}))
    write()
    assert 'TEST' in prior_news(path, at + timedelta(minutes=5))
    assert prior_news(path, at - timedelta(seconds=1)) == prior_news(path, at + timedelta(minutes=15)) == {}
    item['published_at'] = (at-timedelta(hours=2)).isoformat(); write()
    assert prior_news(path, at) == {}
    path.write_text('{}'); assert prior_news(path, at) == {}


@pytest.mark.parametrize('stamp,window', [('2026-11-18T14:44:59+00:00','forming_range'),
    ('2026-11-18T14:45:00+00:00','opening_range'), ('2026-11-18T15:00:00+00:00','opening_continuation'),
    ('2026-11-18T16:10:00+00:00',None), ('2026-10-28T13:45:00+00:00','opening_range'),
    ('2026-11-21T14:45:00+00:00',None)])
def test_windows_follow_new_york_clock(stamp, window):
    assert phase(datetime.fromisoformat(stamp)) == window


def test_hourly_opening_slot_preserves_failure_notification_and_releases_after_checkpoint():
    start = datetime(2026, 11, 18, 14, 1, tzinfo=UTC)
    opening = start.replace(minute=30)
    def brief(now):
        return {'state': 'observed', 'as_of': now.isoformat(), 'window': phase(now), 'open_dublin': opening.isoformat(), 'preparation': []}
    ledger, session = Mock(), Mock()
    session.post.return_value = Mock(status_code=200, json=lambda: {'ok': True, 'result': {'chat': {'id': 123}, 'message_id': 1}})
    active = {'delivery': {'state': 'scanner_snapshot_delivery_confirmed'}, 'opening_session': brief(start)}
    assert notify(active, env=ENV, clock=lambda: start, ledger=ledger, session=session)['state'] == 'collection_notice_waiting_for_opening_checkpoint'
    ledger.reserve.assert_not_called(); session.post.assert_not_called()
    notify({**active,'delivery':{}}, env=ENV, clock=lambda: start, ledger=ledger, session=session)
    assert 'SCANNER FAILURE' in session.post.call_args.kwargs['json']['text']
    checkpoint = opening + timedelta(minutes=15)
    notify({**active, 'opening_session':brief(checkpoint)}, env=ENV, clock=lambda: checkpoint, ledger=ledger, session=session)
    assert '15-minute range' in session.post.call_args.kwargs['json']['text']
    assert not waiting_for_opening_update({**brief(start),'state':'venue_clock_unconfirmed'}, start)
    assert not waiting_for_opening_update(brief(start), start+timedelta(minutes=2))
    assert lines(brief(start), checkpoint) == []


def test_unknown_clock_cannot_yield_preparation_on_a_holiday_or_provider_gap():
    from test_stock_checks import payload
    now = datetime(2026, 11, 26, 14, 0, tzinfo=UTC)
    assert build({}, {}, {}, None, now=now)['state'] == 'venue_clock_unconfirmed'
    p = payload(); p['retrieved_at'] = p['market_clock']['timestamp'] = now.isoformat()
    p['market_clock'].update(is_open=False, next_open=(now+timedelta(days=1,minutes=30)).isoformat(),
                            next_close=(now+timedelta(days=1,hours=7)).isoformat())
    result = build({'stock_reference_checks': {'payload': p, 'payload_sha256': digest(p)}}, {}, {}, None, now=now)
    assert result['state'] == 'no_regular_open_today' and not result['preparation']
    assert not waiting_for_opening_update(result, now)


def test_broad_discovery_routes_an_otherwise_deferred_opening_chart(monkeypatch):
    from market_radar_ai.market_data.discovery import discover
    from test_discovery import Session
    inputs, now = early_input()
    pool = ['S' + chr(65 + i // 26) + chr(65 + i % 26) for i in range(100)]
    eligible = set()
    class Clock(datetime):
        @classmethod
        def now(cls, tz):
            return now.astimezone(tz)
    def histories(symbols, **kwargs):
        return {s: ProviderResult(provider='alpaca_iex', retrieved_at=now,
                candles=[{**b, 'symbol': s, 'volume': '100000' if s in eligible else '10'}
                         for b in inputs['candles']]) for s in symbols}
    monkeypatch.setattr('market_radar_ai.market_data.discovery.datetime', Clock)
    monkeypatch.setattr('market_radar_ai.market_data.discovery_universe.load_universe',
                        lambda **kw: {'symbols': pool, 'failures': []})
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.discover_snapshots',
                        lambda *a, **kw: {'failed_batches': 0, 'ranked_symbols': pool, 'symbol_evidence': {}})
    fetch = Mock(side_effect=histories)
    monkeypatch.setattr('market_radar_ai.market_data.providers.alpaca_batch.fetch_histories', fetch)
    kwargs = dict(env={'ENABLE_BROAD_DISCOVERY':'true','SCREEN_DISCOVERY_DATA':'true',
                  'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture'},
                  now=now, session=Session(now.isoformat()), fallback=[])
    baseline = discover(**kwargs)
    candidate = next(s for s in pool if s not in baseline['selected_symbols'])
    eligible.add(candidate)
    routed = discover(**kwargs)
    route = routed['opening_route']
    assert routed['coverage']['technical_usable'] == 100 and fetch.call_count == 2
    assert len(route['routed_symbols']) == len(route['baseline_symbols']) == 79
    assert (route['chart_matches'], route['baseline_chart_matches'], route['routed_chart_matches']) == (1, 0, 1)
    assert route['baseline_symbols'] == baseline['selected_symbols'] and candidate in routed['selected_symbols']
    row = next(r for r in routed['selection_manifest'] if r['symbol'] == candidate)
    assert row['detail_lane'] == 'opening_range' and row['technical_priority_met'] is False
    assert route['policy'] in routed['selection_policy'] and routed['trade_authorized'] is False


def test_premarket_brief_uses_current_issuer_tagged_news_and_labelled_completed_bars():
    inputs, at = early_input()
    now = at - timedelta(hours=1)
    ref = inputs['reference_checks']['payload']
    ref['retrieved_at'] = ref['market_clock']['timestamp'] = now.isoformat()
    ref['market_clock'].update(is_open=False, next_open=now.replace(hour=14, minute=30, second=0).isoformat())
    bars = [{**b, 'timestamp': (datetime.fromisoformat(b['timestamp']) - timedelta(hours=1)).isoformat()}
            for b in inputs['candles']]
    context = {**inputs['context'], 'intraday': {'bars': bars}, 'retrieved_at': now.isoformat()}
    document = {'stock_reference_checks': {'payload': ref, 'payload_sha256': digest(ref)},
                'stock_context': [{'payload': context, 'payload_sha256': digest(context)}]}
    item = {'kind':'news','title':'Issuer release','source':'wire','url':'https://example.com/issuer',
            'published_at': now.isoformat(), 'retrieved_at':now.isoformat(), 'symbols':['TEST']}
    feed = {'status':'ok','retrieved_at':now.isoformat(),'items':[item]}
    brief = build(document, feed, {}, None, now=now)
    assert [r['symbol'] for r in brief['preparation']] == ['TEST']
    assert 'IEX, through 13:45 Dublin' in ' '.join(lines(brief, now))
    assert not brief['review_ready'] and not brief['trade_authorized']
    item['published_at'] = (now - timedelta(hours=2)).isoformat()
    assert build(document, feed, {}, None, now=now)['preparation'] == []


def test_malformed_optional_opening_notice_preserves_success_delivery():
    now = datetime(2026, 11, 18, 14, 45, tzinfo=UTC)
    transport = Mock()
    transport.post.return_value = Mock(status_code=200, json=lambda: {'ok':True,'result':{'chat':{'id':123},'message_id':1}})
    report = {'delivery':{'state':'scanner_snapshot_delivery_confirmed'}, 'opening_session':{'state':'observed'}}
    receipt = notify(report, env=ENV, clock=lambda: now, ledger=Mock(), session=transport)
    assert receipt['state'] == 'telegram_collection_status_confirmed'
    assert 'Dashboard capture delivered.' in transport.post.call_args.kwargs['json']['text']
