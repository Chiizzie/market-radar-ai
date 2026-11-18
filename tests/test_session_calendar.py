from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from market_radar_ai.market_data.session_calendar import capture_calendar, session_bounds, SOURCE, URL
from market_radar_ai.agents.paper_planner import draft_nvda
from test_paper_planner import inputs, NOW


def evidence(now=NOW, close='16:00'):
    return dict(version='us-equity-calendar-v1', source=SOURCE, observed_at=now.isoformat(),
                date=now.date().isoformat(), status='session', open='09:30', close=close)


def draft(cal, now=NOW):
    return draft_nvda(*inputs(), now=now, paper_capital_eur=500, round_trip_cost_bps=40, calendar=cal)


def test_calendar_clears_only_its_gate_and_buffers_early_close():
    d=draft(evidence(close='13:00'))
    assert d['state']=='conditional_paper_draft'
    assert 'exchange_calendar_not_verified' not in d['blockers']
    assert 'account_specific_eligibility_not_verified' in d['blockers']
    assert 'live_bid_ask_and_costs_not_verified' in d['blockers']
    assert d['plan']['exit_by']=='2026-11-03T17:55:00+00:00'
    assert not d['trade_authorized']


@pytest.mark.parametrize('change', [dict(status='closed'), dict(status='unavailable'),
    dict(date='2026-11-02'), dict(open='16:00', close='09:30'), dict(close='25:00'),
    dict(observed_at='2026-11-03T16:54:59+00:00'), dict(observed_at='2026-11-03T17:00:01+00:00'),
    dict(source='unknown'),dict(observed_at='2026-11-03T17:00:00')])
def test_invalid_calendar_blocks_draft(change):
    assert draft(dict(evidence(),**change))['plan'] is None


def test_close_buffer_blocks_entries_and_premarket_candles():
    assert draft(evidence(close='12:00'))['plan'] is None
    assert draft(dict(evidence(),open='12:00'))['plan'] is None


@pytest.mark.parametrize('day,utc_open', [('2026-03-16',13),('2026-11-03',14)])
def test_dst_uses_new_york_timezone(day,utc_open):
    now=datetime.fromisoformat(day+'T17:00:00+00:00')
    start,end=session_bounds(evidence(now),now=now)
    assert start.astimezone(timezone.utc).hour==utc_open


@pytest.mark.parametrize('rows,status', [([], 'closed'),
    ([{'date':'2026-11-03','open':'09:30','close':'16:00'}], 'session'),
    ([{'date':'2026-11-02','open':'09:30','close':'16:00'}], 'unavailable'),
    ({'error':'secret'}, 'unavailable')])
def test_fixed_get_and_sanitized_result(monkeypatch,rows,status):
    monkeypatch.setenv('ALPACA_API_KEY','test-key');monkeypatch.setenv('ALPACA_API_SECRET','test-secret')
    class Session:
        def get(self,url,**kw):
            assert url==URL and kw['params']=={'start':'2026-11-03','end':'2026-11-03'}
            assert kw['allow_redirects'] is False and kw['timeout']==15
            return type('R',(),{'status_code':200,'json':lambda self:rows})()
    result=capture_calendar(now=NOW,session=Session())
    assert result['status']==status and 'secret' not in str(result)


def test_calendar_is_bound_into_reproducible_review():
    from test_plan_review import data
    from market_radar_ai.agents.alpaca_paper_rehearsal import build
    from market_radar_ai.agents.plan_review import prepare
    c,cat,d=data(); at=datetime.fromisoformat(d['evaluated_at'])
    c['calendar']=evidence(at)
    rebuilt=build(c,cat,d['fx_evidence'],now=at);rebuilt['fx_evidence']=d['fx_evidence']
    prepare(c,cat,rebuilt)
    changed=deepcopy(c);changed['calendar']['close']='13:00'
    with pytest.raises(ValueError):prepare(changed,cat,rebuilt)


@pytest.mark.parametrize('change', [dict(open='09:00'),dict(close='16:01')])
def test_calendar_cannot_expand_regular_hours(change):
    assert draft(dict(evidence(),**change))['plan'] is None


def test_transport_failure_never_exposes_credentials(monkeypatch):
    monkeypatch.setenv('ALPACA_API_KEY','test-key');monkeypatch.setenv('ALPACA_API_SECRET','test-secret')
    class Session:
        def get(self,*args,**kwargs):raise RuntimeError('test-secret')
    result=capture_calendar(now=NOW,session=Session())
    assert result['status']=='unavailable' and 'test-secret' not in str(result)


def test_plan_cannot_outlive_calendar_evidence():
    cal=evidence();cal['observed_at']=(NOW-timedelta(seconds=290)).isoformat()
    assert datetime.fromisoformat(draft(cal)['plan']['expires_at'])==NOW+timedelta(seconds=10)
