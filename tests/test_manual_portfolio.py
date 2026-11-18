from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import gzip
import json

import pytest

from market_radar_ai.agents.candidate_packages import canonical, digest
from market_radar_ai.agents.comparison_live import event_id
from market_radar_ai.agents.event_archive import EventArchive
from market_radar_ai.agents.manual_alert_evidence import PROFILE_PATH, PROTOCOL as CLOCK_PROTOCOL
from market_radar_ai.agents.manual_portfolio import (
    ManualBook, PROTOCOL, EXPERIMENT, CLOCK_ID, replay, collect, validate_bindings,
)
from market_radar_ai.agents.paper_verdict import paper_attempt_id

NOW=datetime(2026,11,16,15,tzinfo=UTC)
PROFILE=json.loads(PROFILE_PATH.read_text())


def setup(symbol='TEST', at=NOW, **changes):
    plan={'symbol':symbol,'entry_eur':'100','stop_eur':'99','target_eur':'110',
        'quantity':'4','fx_rate':'.9','native_currency':'USD','assumed_round_trip_cost_eur':'1.6',
        'expires_at':(at+timedelta(minutes=10)).isoformat(),
        'exit_by':(at+timedelta(hours=1)).isoformat(),**changes}
    body={'candidate_id':'stocks:'+symbol,'symbol':symbol,'assembled_at':at.isoformat(),
        'sources':{},'plan':plan}
    packet={'packet':body,'packet_id':digest(body)}
    decision={'verdict':'PAPER_WATCH_FOR_ENTRY','candidate_id':body['candidate_id'],
        'evaluated_at':at.isoformat(),'plan':plan}
    clock={'schema_version':'manual-alert-clock-v1','protocol_id':CLOCK_ID,
        'source_protocol_id':PROTOCOL['source_protocol_id'],'packet_id':packet['packet_id'],
        'setup_id':paper_attempt_id(packet,now=at),'candidate_id':body['candidate_id'],
        'plan_sha256':digest(plan),'decision_at':at.isoformat(),'request_started_at':at.isoformat(),
        'acknowledged_at':at.isoformat(),'message_sent_at':None,'recorded_at':at.isoformat(),
        'clock_basis':CLOCK_PROTOCOL['clock_basis'],'device_receipt_observed':False,
        'dataset_kind':'forward','trade_authorized':False}
    return body,plan,clock,{'packet':packet,'decision':decision}


def event(seq,kind,payload,at=NOW,*,experiment=None,received=None):
    exp=experiment or PROTOCOL['source_protocol_id']
    row={'seq':seq,'kind':kind,'occurred_at':at.isoformat(),
        'received_at':(received or at).isoformat(),'experiment_id':exp,'day':at.date().isoformat(),
        'payload_json':canonical({**payload,'dataset_kind':'forward','trade_authorized':False})}
    return {**row,'event_id':event_id(exp,row)}


def alert(rows,symbol='TEST',at=NOW,received=None,**changes):
    body,plan,clock,review=setup(symbol,at,**changes)
    rows.append(event(len(rows)+1,'review',review,at))
    rows.append(event(len(rows)+1,'audit',clock,at,experiment=CLOCK_ID,received=received))
    return body,plan,clock


def quote(rows,seconds,bid='100',ask='100.1',symbol='TEST',observed=None):
    at=NOW+timedelta(seconds=seconds)
    rows.append(event(len(rows)+1,'quote',{'candidate_id':'stocks:'+symbol,
        'quote':{'bid':bid,'ask':ask,'observed_at':(observed or at).isoformat()}},at))


def book(report,delay=60,cost='eur_conversion'):
    return next(b for b in report['books'] if b['scenario']==f'{cost}:{delay}')


def evaluate(rows,seconds=360,**kw):
    return replay(rows,now=NOW+timedelta(seconds=seconds),profile=PROFILE,dataset_kind='synthetic',**kw)


def direct(delay=60,cost='usd_balance'):
    return ManualBook(cost,delay,PROFILE)


def tick(b,at,bid='100',ask='100.1',symbol='TEST',observed=None):
    b.quote('stocks:'+symbol,{'bid':bid,'ask':ask,'observed_at':(observed or at).isoformat()},at)


def test_frozen_separate_profile_and_nine_independent_accounts():
    validate_bindings();assert digest(PROTOCOL)==EXPERIMENT
    r=evaluate([])
    assert len(r['books'])==9 and len({b['scenario'] for b in r['books']})==9
    assert all(b['balance_eur']=='1000' and b['closed_net_pnl_eur'] is None for b in r['books'])
    assert not r['trade_authorized'] and not r['costs_verified'] and r['primary_scenario']=='eur_conversion:300'
    assert r['state']=='no_confirmed_alert_clocks'


def test_latency_preserves_original_expiry_and_never_reuses_early_quotes():
    rows=[];alert(rows,expires_at=(NOW+timedelta(seconds=240)).isoformat())
    quote(rows,59);quote(rows,60);quote(rows,61,'111','111.1')
    quote(rows,180);quote(rows,181,'111','111.1')
    r=evaluate(rows)
    assert book(r,60)['closed']==book(r,180)['closed']==1
    assert book(r,300)['blocked_reasons']=={'response_exceeds_entry_window':1}
    for delay,seconds in [(60,60),(180,180)]:
        row=book(r,delay)['details'][0]
        assert row['entry_at']==(NOW+timedelta(seconds=seconds)).isoformat()
        assert D(book(r,delay)['balance_eur'])==D(1000)+D(row['net_pnl_eur'])


def test_shared_cash_and_pending_reservations_do_not_multiply_capital():
    rows=[]
    for symbol in ('A','B','C'):alert(rows,symbol)
    r=evaluate(rows,seconds=1)
    for b in r['books']:
        assert b['states']=={'blocked':1,'reserved':2}
        assert D(b['reserved_capital_eur'])<=1000
        assert D(b['available_capital_eur'])==D(1000)-D(b['reserved_capital_eur'])


def test_duplicate_symbol_and_position_caps_apply_before_response():
    b=direct()
    for symbol,at in [('A',NOW),('A',NOW+timedelta(seconds=1)),('B',NOW+timedelta(seconds=2)),
                      ('C',NOW+timedelta(seconds=3)),('D',NOW+timedelta(seconds=4))]:
        body,plan,c,_=setup(symbol,at,quantity='1')
        b.admit_alert(c,body,plan,at)
    assert b.report(NOW+timedelta(seconds=5))['blocked_reasons']=={'symbol_already_reserved':1,'position_limit':1}


def test_daily_risk_budget_checks_realized_losses_and_existing_reservations():
    b=direct();b.day(NOW)['realized_pnl_eur']=D('-40');b.balance=D(960)
    body,plan,c,_=setup(stop_eur='96',quantity='4',target_eur='120')
    b.admit_alert(c,body,plan,NOW)
    assert b.rows[c['setup_id']]['reason']=='daily_loss_budget'
    body,plan,c,_=setup('SMALL',quantity='1')
    b.admit_alert(c,body,plan,NOW)
    assert b.rows[c['setup_id']]['state']=='reserved'


def test_gap_loss_latches_daily_stop_cancels_pending_and_later_profit_cannot_clear_it():
    rows=[]
    for symbol in ('LOSS','WIN','WAIT'):alert(rows,symbol,quantity='1')
    quote(rows,60,symbol='LOSS');quote(rows,60,symbol='WIN')
    quote(rows,61,'40','40.01',symbol='LOSS')
    quote(rows,62,'200','200.1',symbol='WIN')
    alert(rows,'LATER',NOW+timedelta(seconds=63),quantity='1')
    r=evaluate(rows,seconds=64)
    b=book(r,cost='usd_balance')
    assert D(b['daily_state']['realized_pnl_eur'])>0
    assert b['daily_state']['halt_latched'] and b['halted_days']==1
    assert b['states']=={'blocked':1,'cancelled':1,'closed':2}
    assert b['blocked_reasons']=={'daily_loss_halt':1}
    assert b['details'][0]['net_pnl_eur'] and D(b['details'][0]['net_pnl_eur']) < -50


def test_daily_stop_resets_next_dublin_date_but_balance_does_not():
    b=direct();b.day(NOW).update(realized_pnl_eur=D('-60'),halt_latched=True,halted_at=NOW.isoformat())
    b.balance=D(940)
    tomorrow=NOW+timedelta(days=1)
    body,plan,c,_=setup(at=tomorrow)
    b.admit_alert(c,body,plan,tomorrow)
    assert b.rows[c['setup_id']]['state']=='reserved' and b.balance==940
    assert not b.day(tomorrow)['halt_latched'] and b.days['2026-11-16']['halt_latched']
    assert b.day(tomorrow)['starting_balance_eur']==940


def test_dublin_day_boundary_uses_local_summer_time():
    b=direct();at=datetime(2027,6,1,22,59,tzinfo=UTC)
    b.day(at)['halt_latched']=True
    assert b.day(at+timedelta(minutes=1))['day']=='2027-06-02'
    assert not b.day(at+timedelta(minutes=1))['halt_latched']


@pytest.mark.parametrize('mode',['gap','wide_exit','cutoff'])
def test_unresolved_positions_hold_cash_and_risk_across_days_and_block_entries(mode):
    b=direct();body,plan,c,_=setup(exit_by=(NOW+timedelta(seconds=100)).isoformat())
    b.admit_alert(c,body,plan,NOW);tick(b,NOW+timedelta(seconds=60))
    if mode=='gap':b.advance(NOW+timedelta(seconds=121))
    elif mode=='wide_exit':tick(b,NOW+timedelta(seconds=61),'95','105')
    else:b.advance(NOW+timedelta(seconds=100))
    capital,risk=b.committed()
    tomorrow=NOW+timedelta(days=1)
    body2,plan2,c2,_=setup('NEXT',tomorrow,quantity='1')
    b.admit_alert(c2,body2,plan2,tomorrow)
    assert b.rows[c['setup_id']]['state']=='unresolved' and capital>0 and risk>0
    assert b.committed()==(capital,risk) and b.rows[c2['setup_id']]['reason']=='unresolved_exposure'
    assert b.balance==1000 and b.report(tomorrow)['closed_net_pnl_eur'] is None


def test_pending_entries_recheck_daily_budget_after_another_loss():
    b=direct()
    for symbol in ('LOSS','PENDING'):
        body,plan,c,_=setup(symbol,quantity='4');b.admit_alert(c,body,plan,NOW)
    tick(b,NOW+timedelta(seconds=60),symbol='LOSS')
    tick(b,NOW+timedelta(seconds=61),'88.3','88.31',symbol='LOSS')
    assert -50 < b.day(NOW)['realized_pnl_eur'] < -45
    tick(b,NOW+timedelta(seconds=62),symbol='PENDING')
    row=next(r for r in b.rows.values() if r['candidate_id']=='stocks:PENDING')
    assert row['state']=='cancelled' and row['reason']=='daily_loss_budget'


def test_stop_invalidation_before_manual_response_stays_invalid_after_recovery():
    rows=[];alert(rows);quote(rows,30,'98','98.1');quote(rows,60)
    r=evaluate(rows)
    assert all(b['states']=={'invalidated':1} and b['reserved_capital_eur']=='0' for b in r['books'])


def test_stop_between_acknowledgement_and_late_clock_storage_is_not_forgotten():
    _,_,clock,review=setup()
    rows=[event(1,'review',review)]
    quote(rows,10,'98','98.1')
    rows.append(event(3,'audit',clock,experiment=CLOCK_ID,received=NOW+timedelta(seconds=20)))
    quote(rows,60)
    assert all(b['states']=={'invalidated':1} for b in evaluate(rows)['books'])


def test_exact_daily_limit_prevents_admission_and_profits_do_not_expand_open_risk():
    b=direct();b.day(NOW)['realized_pnl_eur']=D('-50');b.balance=D(950)
    body,plan,c,_=setup();b.admit_alert(c,body,plan,NOW)
    assert b.rows[c['setup_id']]['reason']=='daily_loss_halt'
    b=direct();b.balance=D(2000);b.day(NOW)['realized_pnl_eur']=D(1000)
    for symbol in ('A','B','C'):
        body,plan,c,_=setup(symbol,stop_eur='90',target_eur='150',quantity='1.9')
        b.admit_alert(c,body,plan,NOW)
    assert b.rows[c['setup_id']]['reason']=='combined_risk_limit' and b.committed()[1]<=40


def test_session_cutoff_and_weekend_do_not_expand_with_all_day_availability():
    for at in [datetime(2026,11,16,21,59,30,tzinfo=UTC),datetime(2026,11,21,15,tzinfo=UTC)]:
        b=direct();body,plan,c,_=setup(at=at)
        b.admit_alert(c,body,plan,at)
        assert b.rows[c['setup_id']]['reason']=='manual_session_or_intraday_cutoff'


def test_scheduled_exit_is_before_cutoff_and_late_received_exit_stays_unknown():
    for received in (80,101):
        rows=[];alert(rows,exit_by=(NOW+timedelta(seconds=100)).isoformat())
        quote(rows,60);quote(rows,received,'100','100.1',observed=NOW+timedelta(seconds=80))
        b=book(evaluate(rows,seconds=102))
        assert b['states']==({'closed':1} if received==80 else {'unresolved':1})


@pytest.mark.parametrize('bid,ask',[('100','101'),('101','101.1'),('99.5','99.6')])
def test_spread_chasing_and_untriggered_quotes_do_not_fill(bid,ask):
    rows=[];alert(rows);quote(rows,60,bid,ask)
    assert book(evaluate(rows))['states']=={'reserved':1}


def test_delayed_acknowledgement_receipt_cannot_reuse_old_quote():
    rows=[];alert(rows,received=NOW+timedelta(seconds=90))
    quote(rows,100,observed=NOW+timedelta(seconds=60))
    assert book(evaluate(rows))['states']=={'reserved':1}


def test_same_exchange_observation_cannot_enter_and_exit_or_move_backwards():
    rows=[];alert(rows);quote(rows,60);quote(rows,61,'111','111.1',observed=NOW+timedelta(seconds=60))
    assert book(evaluate(rows,seconds=61))['states']=={'open':1}


def test_missing_source_review_and_future_events_are_not_invented():
    body,plan,c,review=setup()
    rows=[event(1,'audit',c,experiment=CLOCK_ID)]
    r=evaluate(rows)
    assert r['unmatched_clocks']==1 and all(b['considered']==0 for b in r['books'])
    rows.append(event(2,'review',review,received=NOW+timedelta(seconds=500)))
    assert evaluate(rows)['unmatched_clocks']==1


def test_tampered_binding_unknown_source_and_conflicting_duplicate_fail_closed():
    rows=[];alert(rows)
    bad=deepcopy(rows);p=json.loads(bad[0]['payload_json']);p['decision']['plan']['entry_eur']='101'
    bad[0]=event(1,'review',p)
    with pytest.raises(ValueError,match='binding'):evaluate(bad)
    bad=deepcopy(rows);bad[0]['experiment_id']='f'*64
    with pytest.raises(ValueError,match='identity'):evaluate(bad)
    bad=deepcopy(rows[0]);bad['received_at']=(NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match='duplicate'):evaluate(rows+[bad])


def test_restart_and_lossless_archive_reproduce_balances_halts_and_full_ledger(tmp_path):
    rows=[];alert(rows);quote(rows,60);quote(rows,61,'80','80.1')
    original=[];r=evaluate(rows,seconds=62,ledger_output=original)
    archive_path=tmp_path/'source.jsonl.gz'
    with gzip.open(archive_path,'wt') as out:
        for row in rows:out.write(canonical(row)+'\n')
    with EventArchive() as archive:
        with gzip.open(archive_path,'rt') as inp:
            for line in inp:archive.append(json.loads(line))
        recovered=[]
        assert replay(archive,now=NOW+timedelta(seconds=62),profile=PROFILE,
            dataset_kind='synthetic',ledger_output=recovered)==r
        assert recovered==original and archive.source_digest()==digest(rows)
    duplicate=evaluate(rows+[rows[0]],seconds=62)
    assert duplicate['books']==r['books'] and duplicate['clocks']==1
    assert book(r)['daily_state']['halt_latched']


def test_collector_reads_only_clocks_until_any_exist_and_before_start_does_no_read(tmp_path):
    class Client:
        def __init__(self):self.calls=[]
        def read(self,experiment,day,after):
            self.calls.append((experiment,day,after));return {'events':[],'next':after}
    client=Client();diagnostics=[]
    with collect(client,now=NOW-timedelta(days=2),root=tmp_path,diagnostics=diagnostics) as archive:
        assert len(archive)==0 and client.calls==[]
    with collect(client,now=NOW+timedelta(days=1),root=tmp_path,diagnostics=diagnostics) as archive:
        assert len(archive)==0
    assert client.calls==[(CLOCK_ID,'2026-11-16',0),(CLOCK_ID,'2026-11-17',0)]
    assert all(d['source_loaded'] is False for d in diagnostics)


def test_expired_fees_and_unsupported_market_remain_blocked():
    b=direct();at=datetime(2026,12,8,15,tzinfo=UTC)
    body,plan,c,_=setup(at=at);b.admit_alert(c,body,plan,at)
    assert b.rows[c['setup_id']]['reason']=='fee_schedule_stale'
    b=direct();body,plan,c,_=setup(native_currency='EUR');b.admit_alert(c,body,plan,NOW)
    assert b.rows[c['setup_id']]['reason']=='cost_model_unavailable_for_market'


def test_full_guarded_review_clock_collection_and_restore_contract(tmp_path,monkeypatch):
    import test_pullback_strategy as fixture_source
    original=fixture_source.archived
    def shifted():
        bars,at=original();delta=timedelta(days=10)
        return [b.model_copy(update={'timestamp':b.timestamp+delta}) for b in bars],at+delta
    monkeypatch.setattr(fixture_source,'archived',shifted)
    from test_quote_policy_rollout import packet_fixture
    from market_radar_ai.agents.paper_verdict import finalize,export_archive
    from market_radar_ai.agents.comparison_live import LiveComparison,envelope
    from market_radar_ai.agents.manual_alert_evidence import record_ack
    from market_radar_ai.agents.paper_comparison import GUARDED_PROTOCOL
    doc,feed,at,packet,audit=packet_fixture();current=[at]
    class Client:
        def __init__(self):self.rows=[]
        def append(self,experiment,events):
            for e in events:
                self.rows.append({**e,'event_id':event_id(experiment,e),'experiment_id':experiment,
                    'day':e['occurred_at'][:10],'seq':len(self.rows)+1,'received_at':current[0].isoformat()})
        def read(self,experiment,day,after):
            page=[e for e in self.rows if e['experiment_id']==experiment and e['day']==day and e['seq']>after][:3]
            return {'events':page,'next':page[-1]['seq'] if page else after}
    client=Client()
    source=LiveComparison(tmp_path/'writer',client=client,clock=lambda:current[0],day=at.date().isoformat(),protocol=GUARDED_PROTOCOL)
    source.enrol(packet,now=at);source.begin_review(packet,now=at)
    decision=finalize(packet,audit,doc,feed,now=at)
    source.record_review(packet,audit,decision,now=at)
    record_ack(export_archive(packet,audit,decision),request_started_at=at,acknowledged_at=at,
        recorded_at=at,provider_date=None,client=client)
    for seconds,price in [(60,decision['plan']['entry_eur']),(61,decision['plan']['target_eur'])]:
        current[0]=at+timedelta(seconds=seconds)
        client.append(PROTOCOL['source_protocol_id'],[envelope('quote',{
            'candidate_id':decision['candidate_id'],'quote':{'bid':price,'ask':price,'observed_at':current[0].isoformat()},
            'source':'alpaca_iex:'+'a'*64,'received_at':current[0].isoformat()},current[0])])
    diagnostics=[]
    with collect(client,now=at+timedelta(seconds=62),root=tmp_path/'reader',diagnostics=diagnostics) as archive:
        r=replay(archive,now=at+timedelta(seconds=62),profile=PROFILE,dataset_kind='synthetic')
        assert r['matched_clocks']==1 and book(r,cost='usd_balance')['closed']==1, [(b['scenario'],b['states'],b['blocked_reasons']) for b in r['books']]
        assert diagnostics==[{'day':'2026-11-16','clocks':1,'source_loaded':True}]
        assert r['source_events']==6


def test_disk_capacity_refuses_partial_account_reconstruction():
    with EventArchive(max_bytes=20) as archive:
        with pytest.raises(ValueError,match='capacity'):
            archive.append({'seq':1,'payload_json':'x'*50})
        assert len(archive)==0


def test_report_stays_bounded_and_totals_retain_omitted_setups():
    rows=[]
    for n in range(200):alert(rows,f'S{n:04}',quantity='1')
    r=evaluate(rows,seconds=1)
    assert len(canonical(r).encode())<175000
    assert all(b['considered']==200 and len(b['details'])==8 and b['details_omitted']==192 for b in r['books'])
