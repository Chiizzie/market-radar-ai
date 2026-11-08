import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from market_radar_ai.agents.execution_research import Book, PROFILES, PROTOCOL, fees, replay, size, estimate
from market_radar_ai.agents.candidate_packages import digest

NOW = datetime(2026, 11, 9, 15, tzinfo=UTC)


def plan(symbol='AAPL', **changes):
    return {'symbol':symbol, 'entry_eur':'100', 'stop_eur':'99', 'target_eur':'105',
        'quantity':'4', 'fx_rate':'0.9', 'native_currency':'USD',
        'expires_at':(NOW+timedelta(seconds=60)).isoformat(),
        'exit_by':(NOW+timedelta(hours=1)).isoformat(),
        'assumed_round_trip_cost_eur':'1.6', **changes}


def body(symbol='AAPL', **changes):
    return {'candidate_id':'stocks:'+symbol, 'symbol':symbol, 'assembled_at':NOW.isoformat(),
        'sources':{}, 'plan':plan(symbol, **changes)}


def event(seq, kind, payload, seconds=0, received=None):
    at = NOW+timedelta(seconds=seconds)
    raw=json.dumps(payload, sort_keys=True)
    return {'seq':seq, 'event_id':digest([seq,kind,raw]), 'kind':kind,
        'occurred_at':at.isoformat(), 'received_at':(received or at).isoformat(), 'payload_json':raw}


def enrol(seq, symbol='AAPL', seconds=0, **changes):
    return event(seq,'enrol',{'packet':{'packet':body(symbol,**changes)}},seconds)


def quote(seq, bid, ask=None, seconds=1, received=None, symbol='AAPL'):
    return event(seq,'quote',{'candidate_id':'stocks:'+symbol,
        'quote':{'bid':str(bid),'ask':str(ask if ask is not None else bid),
                 'observed_at':(NOW+timedelta(seconds=seconds)).isoformat()}},seconds,received)


def test_fees_and_routes_do_not_double_charge_spread():
    f=fees('eur_conversion',entry=D(100),exit_price=D(110),quantity=D(4),fx=D('.9'))
    assert f=={'entry_fx_eur':D('.60'),'exit_fx_eur':D('.66'),'us_sale_levies_eur':D('.01')}
    native=fees('usd_balance',entry=D(100),exit_price=D(110),quantity=D(4),fx=D('.9'))
    assert native['entry_fx_eur']==native['exit_fx_eur']==0
    assert set(f)=={'entry_fx_eur','exit_fx_eur','us_sale_levies_eur'}


@pytest.mark.parametrize('profile',PROFILES)
def test_sizing_preserves_target_and_risk_cap(profile):
    p=plan(quantity='100'); original=deepcopy(p)
    e=size(profile,p)
    assert e['capital']<=500 and e['risk']<=20 and e['quantity']<=D(p['quantity'])
    assert p==original


def test_cost_sensitivity_keeps_structure_and_can_reject():
    p=plan(target_eur='103')
    assert estimate('usd_balance',p)['rr']>estimate('eur_conversion',p)['rr']>estimate('stressed',p)['rr']
    b=Book('stressed','code_only'); b.admit('a',body(target_eur='103'),p,NOW)
    assert b.rows['a']['reason']=='scenario_net_reward_below_2r'
    assert b.committed()==(0,0)


def test_capital_is_shared_and_expired_reservations_release():
    b=Book('usd_balance','code_only')
    for s in ('A','B','C'): b.admit(s,body(s),plan(s),NOW)
    assert b.rows['C']['reason']=='insufficient_shared_capital'
    assert b.committed()[0]<=1000
    b.advance(NOW+timedelta(seconds=60))
    assert b.committed()==(0,0) and b.balance==1000
    assert b.rows['A']['state']=='expired'


def test_total_risk_position_and_duplicate_limits():
    b=Book('usd_balance','code_only')
    for s in ('A','B','C'):
        p=plan(s,stop_eur='90',target_eur='140',quantity='1.9')
        b.admit(s,body(s),p,NOW)
    assert b.rows['C']['reason']=='combined_risk_limit' and b.committed()[1]<=40
    c=Book('usd_balance','code_only')
    c.admit('a',body(),plan(quantity='1'),NOW)
    c.admit('duplicate',body(),plan(quantity='1'),NOW)
    assert c.rows['duplicate']['reason']=='symbol_already_reserved'
    for s in ('B','C','D'): c.admit(s,body(s),plan(s,quantity='1'),NOW)
    assert c.rows['D']['reason']=='position_limit'


def test_closed_ledger_reconciles_fees_slippage_and_capital():
    events=[enrol(1),quote(2,100,100.1),quote(3,106,seconds=2)]
    r=replay(events,now=NOW+timedelta(seconds=3),dataset_kind='synthetic')
    for b in r['books']:
        if b['arm']=='ai_reviewed': assert b['considered']==0; continue
        x=b['details'][0]
        assert b['closed']==1 and D(b['balance_eur'])==1000+D(x['net_pnl_eur'])
        assert D(b['available_capital_eur'])==D(b['balance_eur']) and D(b['reserved_capital_eur'])==0
        assert D(x['net_pnl_eur'])==(D(x['exit_eur'])-D(x['entry_eur']))*D(x['quantity'])-D(x['closed_fees_eur'])
        assert D(x['closed_slippage_eur'])>0 and D(x['entry_spread_bps'])>0
    assert r['ai_cost_incomplete_cohorts']==1


def test_ai_can_only_enter_after_durable_approval_and_cannot_reuse_old_quotes():
    packet={'packet':body()}
    decision={'verdict':'PAPER_WATCH_FOR_ENTRY','plan':plan()}
    events=[enrol(1),quote(2,100,seconds=1),quote(3,106,seconds=2),
        event(4,'review',{'packet':packet,'decision':decision},3),
        quote(5,100,seconds=1,received=NOW+timedelta(seconds=4))]
    r=replay(events,now=NOW+timedelta(seconds=61),dataset_kind='synthetic')
    assert all(b['closed']==1 if b['arm']=='code_only' else b['states']=={'expired':1} for b in r['books'])


def test_no_late_exit_and_unresolved_reservations_survive_days():
    end=NOW+timedelta(hours=1)
    events=[enrol(1),quote(2,100),quote(3,105,seconds=3599,received=end+timedelta(seconds=1))]
    r=replay(events,now=NOW+timedelta(days=1),dataset_kind='synthetic')
    for b in r['books']:
        if b['arm']=='code_only':
            assert b['states']=={'unresolved':1} and D(b['reserved_capital_eur'])>0
            assert b['closed_net_pnl_eur'] is None and b['balance_eur']=='1000'


def test_exit_before_cutoff_and_stop_gap_realized_loss_can_exceed_plan():
    r=replay([enrol(1),quote(2,100),quote(3,80,seconds=2)],now=NOW+timedelta(seconds=3),dataset_kind='synthetic')
    assert all(D(b['closed_net_pnl_eur']) < -20 for b in r['books'] if b['arm']=='code_only')
    r=replay([enrol(1),quote(2,100),quote(3,100,seconds=3580)],now=NOW+timedelta(hours=1),dataset_kind='synthetic')
    assert all(b['details'][0]['reason']=='scheduled_exit' for b in r['books'] if b['arm']=='code_only')


@pytest.mark.parametrize('bid,ask', [('100','101'),('101','101')])
def test_wide_spread_and_chasing_cannot_fill(bid,ask):
    r=replay([enrol(1),quote(2,bid,ask)],now=NOW+timedelta(seconds=61),dataset_kind='synthetic')
    assert all(b['states']=={'expired':1} for b in r['books'] if b['arm']=='code_only')


def test_stop_cross_before_entry_releases_capital():
    r=replay([enrol(1),quote(2,98)],now=NOW+timedelta(seconds=3),dataset_kind='synthetic')
    assert all(b['states']=={'invalidated':1} and b['reserved_capital_eur']=='0' for b in r['books'] if b['arm']=='code_only')


def test_unknown_market_and_stale_fee_schedule_are_not_free():
    b=Book('eur_conversion','code_only'); p=plan(native_currency='EUR')
    b.admit('a',body(),p,NOW)
    assert b.rows['a']['reason']=='cost_model_unavailable_for_market'
    b.admit('b',body(),plan(),datetime(2026,12,8,tzinfo=UTC))
    assert b.rows['b']['reason']=='fee_schedule_stale'


def test_duplicate_and_order_recovery_are_deterministic_empty_is_unknown():
    e=[enrol(1),quote(2,100),quote(3,106,seconds=2)]
    now=NOW+timedelta(seconds=3)
    a=replay(e,now=now,dataset_kind='synthetic')
    b=replay([e[2],e[0],e[1],e[0]],now=now,dataset_kind='synthetic')
    assert a['books']==b['books']
    empty=replay([],now=now)
    assert all(b['closed_net_pnl_eur'] is None and b['balance_eur']=='1000' for b in empty['books'])
    assert empty['source_cohorts']==0 and not empty['trade_authorized'] and not empty['costs_verified']


def test_rejected_ai_review_never_creates_a_position():
    r=replay([enrol(1),event(2,'review',{'packet':{'packet':body()},'decision':{'verdict':'NO_ACTION'}},1)],
        now=NOW+timedelta(seconds=2),dataset_kind='synthetic')
    assert all(b['considered']==0 for b in r['books'] if b['arm']=='ai_reviewed')
