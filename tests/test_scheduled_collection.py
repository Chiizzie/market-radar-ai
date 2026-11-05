from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import pytest

from market_radar_ai.dashboard.collection_schedule import collection_window, scheduled_scope, WORKFLOW_REF
from market_radar_ai.dashboard.scheduled_collection import (
    STOCKS, digest, load_cache, run_cycle, write_json,
)
from market_radar_ai.evidence.earnings_calendar import CalendarCapture
from market_radar_ai.dashboard.snapshot_delivery import deliver
from test_snapshot_delivery import Session, ENV as MANUAL_ENV
from test_dashboard_cache import capture

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
ENV = {**MANUAL_ENV, 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'schedule',
       'GITHUB_WORKFLOW_REF': WORKFLOW_REF, 'SCANNER_COLLECTION_MODE': 'scheduled'}


@pytest.mark.parametrize('stamp,expected', [
    ('2026-11-04T07:59:59+00:00', False), ('2026-11-04T08:00:00+00:00', True),
    ('2026-11-04T22:59:59+00:00', True), ('2026-11-04T23:00:00+00:00', False),
    ('2026-07-04T06:59:59+00:00', False), ('2026-07-04T07:00:00+00:00', False),
    ('2026-07-04T21:59:59+00:00', False), ('2026-07-04T22:00:00+00:00', False),
    ('2026-03-29T07:00:00+00:00', False), ('2026-10-25T07:00:00+00:00', False),
])
def test_irish_hours_include_dst_and_weekends(stamp, expected):
    assert collection_window(datetime.fromisoformat(stamp)) is expected


def test_naive_clock_and_no_automatic_outside_hours_override():
    with pytest.raises(ValueError): collection_window(datetime(2026, 11, 4))
    late = NOW.replace(hour=23)
    assert not scheduled_scope({**ENV, 'SCANNER_VERIFY_OUTSIDE_WINDOW': 'true'}, late)
    assert scheduled_scope({**ENV, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                            'SCANNER_VERIFY_OUTSIDE_WINDOW': 'true'}, late)


@pytest.mark.parametrize('field,value', [
    ('GITHUB_REPOSITORY', 'Chiizzie/market-radar'), ('GITHUB_REF', 'refs/heads/other'),
    ('GITHUB_WORKFLOW_REF', 'wrong'), ('GITHUB_EVENT_NAME', 'push'),
    ('GITHUB_RUN_ATTEMPT', '2'), ('SCANNER_COLLECTION_MODE', 'paid'),
])
def test_schedule_cannot_expand_repository_workflow_or_retry_scope(field, value):
    env = {**ENV, field: value}
    assert not scheduled_scope(env, NOW)
    session = Session()
    with pytest.raises(ValueError): deliver(capture(), env=env, clock=lambda: NOW, session=session)
    assert session.calls == []


def test_scheduled_delivery_retains_strict_expiry_and_no_action():
    s = Session()
    receipt = deliver(capture(), env=ENV, clock=lambda: NOW, session=s)
    assert receipt['expires_at_epoch'] == int(NOW.timestamp())+60
    doc = json.loads(s.calls[0]['data'])
    assert not doc['live_orders_enabled'] and doc['agents']['reports'] == []
    assert all(r['decision'] == 'NO_ACTION' for rows in doc['markets'].values() for r in rows)


def evidence():
    news = {'status': 'ok', 'items': [], 'retrieved_at': NOW.isoformat(), 'scope': 'test'}
    calendars = []
    for symbol in STOCKS:
        p = CalendarCapture(symbol=symbol, retrieved_at=NOW, request_from=NOW.date(),
                            request_to=NOW.date(), status='empty', raw_payload_sha256='a'*64).model_dump(mode='json')
        calendars.append({'payload': p, 'payload_sha256': digest(p)})
    return news, calendars


def cached(path):
    news, calendars = evidence()
    payload = {'version': 1, 'stocks': list(STOCKS), 'collection_started_at': NOW.isoformat(),
               'news': news, 'calendars': calendars}
    write_json(path, {'payload': payload, 'sha256': digest(payload)})
    return payload


def test_cache_reuse_preserves_all_source_times_then_refreshes_at_15_minutes(tmp_path):
    path = tmp_path/'cache.json'; original = cached(path)
    for minutes in (0, 5, 10, 14.99):
        assert load_cache(path, NOW+timedelta(minutes=minutes)) == original
    assert load_cache(path, NOW+timedelta(minutes=15)) is None
    assert load_cache(path, NOW-timedelta(seconds=1)) is None


@pytest.mark.parametrize('fault', ['checksum', 'symbol', 'future', 'naive', 'oversize', 'invalid'])
def test_bad_cache_is_never_reused(tmp_path, fault):
    path = tmp_path/'cache.json'; payload = cached(path)
    if fault == 'oversize': path.write_text('x'*2_000_001)
    elif fault == 'invalid': path.write_text('no json')
    else:
        if fault == 'checksum': payload['news']['scope'] = 'tampered'
        if fault == 'symbol': payload['stocks'] = ['OTHER']
        if fault == 'future': payload['calendars'][0]['payload']['retrieved_at'] = (NOW+timedelta(seconds=1)).isoformat()
        if fault == 'naive': payload['collection_started_at'] = '2026-11-04T12:00:00'
        write_json(path, {'payload': payload, 'sha256': 'bad' if fault == 'checksum' else digest(payload)})
    assert load_cache(path, NOW) is None


def fake_stages(calls, fail=None):
    def run(module, args):
        calls.append(module)
        path = args[args.index('--output')+1]
        news, calendars = evidence()
        body = news if module == 'evidence.scanner_feed' else {'earnings_calendars': calendars}
        write_json(path, body)
        return 1 if module == fail else 0
    return run


def test_two_cycles_refresh_markets_but_reuse_news_and_calendar(tmp_path):
    calls = []; deliveries = []; clock = [NOW]
    def delivery(doc, **kw):
        deliveries.append(deepcopy((doc, kw['evidence'])))
        return {'state': 'scanner_snapshot_delivery_confirmed', 'snapshot_id': str(len(deliveries))}
    common = dict(env=ENV, cache_path=tmp_path/'cache.json', clock=lambda: clock[0],
                  run=fake_stages(calls), delivery=delivery)
    a = run_cycle(output=tmp_path/'first', **common)
    clock[0] += timedelta(minutes=5)
    b = run_cycle(output=tmp_path/'second', **common)
    assert a['evidence_cache'] == 'collected' and b['evidence_cache'] == 'reused_original_timestamps'
    assert calls.count('market_data.capture') == 2
    assert calls.count('evidence.scanner_feed') == calls.count('evidence.earnings_calendar') == 1
    assert deliveries[0] == deliveries[1]
    assert not any('review' in c or 'openai' in c for c in calls)
    assert b['model_calls'] == 0 and not b['trade_authorized']


def test_provider_failure_is_reported_even_after_successful_delivery(tmp_path):
    r = run_cycle(env=ENV, output=tmp_path/'out', cache_path=tmp_path/'cache.json',
        clock=lambda: NOW, run=fake_stages([], fail='market_data.capture'),
        delivery=lambda *a, **k: {'state': 'scanner_snapshot_delivery_confirmed'})
    assert r['state'] == 'delivered_with_failures' and r['failures'] == ['market']


@pytest.mark.parametrize('key', ['OPENAI_API_KEY', 'OPEN_API_KEY', 'GH_BUDGET_TOKEN'])
def test_scheduled_collector_refuses_paid_credentials_before_any_call(tmp_path, key):
    calls = []
    with pytest.raises(ValueError, match='paid_credentials'):
        run_cycle(env={**ENV, key: 'test'}, output=tmp_path/'out', cache_path=tmp_path/'cache',
                  clock=lambda: NOW, run=fake_stages(calls))
    assert calls == []


def test_cache_cannot_cross_dynamic_shortlists(tmp_path):
    path=tmp_path/'cache.json'
    cached(path)
    assert load_cache(path,NOW,stocks=('OTHER',)) is None


def test_dynamic_discovery_symbols_reach_news_and_market(tmp_path,monkeypatch):
    selected=('IBM','ORCL')
    watched=(*selected,'MU')
    monkeypatch.setattr('market_radar_ai.market_data.discovery.discover',lambda **k:{'selected_symbols':list(selected),'status':'ok'})
    def run(module,args):
        path=args[args.index('--output')+1]
        if module=='evidence.scanner_feed':
            assert args[args.index('--symbols')+1:]==list(watched)
            body={'status':'ok','items':[],'retrieved_at':NOW.isoformat(),'scope':'test'}
        else:
            if module=='market_data.capture':
                assert args[args.index('--stocks')+1:args.index('--crypto')]==list(watched)
            rows=[]
            for symbol in watched:
                p=CalendarCapture(symbol=symbol,retrieved_at=NOW,request_from=NOW.date(),request_to=NOW.date(),status='empty',raw_payload_sha256='a'*64).model_dump(mode='json')
                rows.append({'payload':p,'payload_sha256':digest(p)})
            body={'earnings_calendars':rows}
        write_json(path,body)
        return 0
    report=run_cycle(env={**ENV,'ENABLE_STOCK_DISCOVERY':'true'},output=tmp_path/'out',cache_path=tmp_path/'cache.json',clock=lambda:NOW,run=run,delivery=lambda *a,**k:{'state':'scanner_snapshot_delivery_confirmed'})
    assert report['stock_discovery']['selected_symbols']==list(selected)
    assert load_cache(tmp_path/'cache.json',NOW,watched) is not None


@pytest.mark.parametrize('cached_evidence',[False,True])
def test_short_lived_quotes_follow_slow_checks(tmp_path,cached_evidence):
    calls=[]
    cache=tmp_path/'cache.json'
    if cached_evidence:
        cached(cache)
    run_cycle(env={**ENV,'ENABLE_STOCK_CHECKS':'true'}, output=tmp_path/'out',
              cache_path=cache, clock=lambda:NOW, run=fake_stages(calls),
              delivery=lambda *a,**k:{'state':'scanner_snapshot_delivery_confirmed'})
    assert calls.index('market_data.stock_checks') < calls.index('market_data.reference_quotes')
    assert calls.index('market_data.reference_quotes') < calls.index('agents.qualification')
    assert calls.count('market_data.reference_quotes')==1
    if not cached_evidence:
        assert calls.index('evidence.earnings_calendar') < calls.index('market_data.reference_quotes')


def test_active_paper_symbols_survive_discovery_rotation(tmp_path,monkeypatch):
    import market_radar_ai.agents.github_paper_tracking as journal
    seen=[]
    def update(token,**kwargs):
        seen.append(kwargs)
        return {'trades':[{'symbol':'TRACKED','state':'open_simulation'}]}
    monkeypatch.setattr(journal,'update',update)
    def run(module,args):
        if module=='market_data.capture':assert args[args.index('--stocks')+1]=='TRACKED'
        return fake_stages([])(module,args)
    # Seed a matching cache to keep this fixture's calendar universe coherent.
    news,calendars=evidence()
    stocks=('TRACKED',*STOCKS)
    from market_radar_ai.dashboard import scheduled_collection as collection
    monkeypatch.setattr(collection,'load_cache',lambda *a,**k:{'news':news,'calendars':calendars,'collection_started_at':NOW.isoformat()})
    run_cycle(env={**ENV,'GH_PAPER_TOKEN':'fixture'}, output=tmp_path/'run',cache_path=tmp_path/'cache',
              clock=lambda:NOW,run=run,delivery=lambda *a,**k:{'state':'fixture'})
    assert len(seen)==2 and 'capture' in seen[1]
    assert (tmp_path/'run/paper-tracking.json').exists()
