"""Synthetic offline checks; never calls providers or mutates remote research."""
from copy import deepcopy
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace
import json
import pytest
from test_strategy_experiment import fixture as old_fixture, Events
from market_radar_ai.agents.entry_confirmation import (
    PROTOCOL_ID, PROTOCOL, VARIANT, ARMS, common, outcomes, build_report, coverage,
)
from market_radar_ai.agents.entry_confirmation_live import EntryExperiment
from market_radar_ai.agents.strategy_experiment import build, replay, D
from market_radar_ai.agents.comparison_live import envelope
from market_radar_ai.agents.candidate_packages import digest

NOW = datetime(2026,11,13,16,10,1,tzinfo=UTC)


def fixture():
    f=json.loads(json.dumps(old_fixture()).replace('2026-11-12', '2026-11-13'))
    f['reference_checks']['payload']['market_clock']['next_open']='2026-11-16T14:30:00Z'
    f['reference_checks']['payload_sha256']=digest(f['reference_checks']['payload'])
    return f


def cohort():
    return {**build(fixture(),now=NOW), 'enrolled_at':NOW.isoformat()}


def quote(c,bid,ask=None,seconds=1,durable_delay=0):
    at=NOW+timedelta(seconds=seconds)
    fx=D(c['variants'][VARIANT]['plan']['fx_rate'])
    bid,ask=D(bid),D(ask if ask is not None else bid)
    return {**common(),'candidate_id':c['candidate_id'],
            'quote':{'observed_at':at.isoformat(),'bid':str(bid*fx),'ask':str(ask*fx)},
            'received_at':at.isoformat(),'durable_received_at':(at+timedelta(seconds=durable_delay)).isoformat(),
            'native_quote_usd':{'bid':str(bid),'ask':str(ask)},'eur_per_usd':str(fx),'source':'alpaca_iex:'+'a'*64}


def test_ask_crossing_alone_cannot_fill_bid_arm_and_control_is_unchanged():
    c=cohort();p=c['variants'][VARIANT]['plan'];entry=D(p['entry_usd'])
    q=quote(c,entry-D('.01'),entry)
    r=outcomes(c,[q],NOW+timedelta(seconds=2))
    assert r['ask_trigger']['state']=='open'
    assert r['bid_confirmed']['state']=='watching'
    assert r['ask_trigger']==replay(c,[q],now=NOW+timedelta(seconds=2))[VARIANT]


def test_later_bid_confirmation_uses_later_actual_ask_and_costs():
    c=cohort();p=c['variants'][VARIANT]['plan'];entry=D(p['entry_usd']);target=D(p['target_usd'])
    quotes=[quote(c,entry-D('.01'),entry),quote(c,entry,entry+D('.01'),seconds=6),
            quote(c,target,target+D('.01'),seconds=11)]
    pair=outcomes(c,quotes,NOW+timedelta(seconds=12))
    assert all(r['state']=='closed' for r in pair.values())
    assert pair['bid_confirmed']['entry_at']==(NOW+timedelta(seconds=6)).isoformat()
    assert D(pair['bid_confirmed']['entry_usd'])>D(pair['ask_trigger']['entry_usd'])
    assert D(pair['bid_confirmed']['net_pnl_eur'])<D(pair['ask_trigger']['net_pnl_eur'])
    assert coverage(quotes,pair)['paired_adequate'] is True


@pytest.mark.parametrize('fault',['wide','gap','stale','before_enrol','after_expiry'])
def test_confirmation_does_not_bypass_common_quote_or_entry_rules(fault):
    c=cohort();entry=D(c['variants'][VARIANT]['plan']['entry_usd'])
    q=quote(c,entry,entry+D('.01'))
    if fault=='wide':q=quote(c,entry,entry+5)
    if fault=='gap':q=quote(c,entry*D('1.003'),entry*D('1.003'))
    if fault=='stale':q=quote(c,entry,seconds=1,durable_delay=61)
    if fault=='before_enrol':q=quote(c,entry,seconds=-1)
    if fault=='after_expiry':q=quote(c,entry,seconds=179,durable_delay=2)
    pair=outcomes(c,[q],NOW+timedelta(seconds=200))
    assert all(r['entry_at'] is None for r in pair.values())


def test_wide_exit_and_no_exit_remain_unresolved():
    c=cohort();p=c['variants'][VARIANT]['plan'];entry=D(p['entry_usd']);target=D(p['target_usd'])
    qs=[quote(c,entry),quote(c,target,target+5,seconds=6)]
    pair=outcomes(c,qs,NOW+timedelta(seconds=10))
    assert all(r['state']=='unresolved' and r['net_pnl_eur'] is None for r in pair.values())
    pair=outcomes(c,qs[:1],datetime.fromisoformat(p['exit_by'])+timedelta(seconds=1))
    assert all(r['state']=='unresolved' for r in pair.values())


def test_durable_recovery_freezes_cohort_and_allows_no_duplicate_enrolment(tmp_path):
    client=Events();clock=[NOW]
    one=EntryExperiment(tmp_path/'one',client=client,clock=lambda:clock[0])
    one.enrol([fixture()],capture_sha='a'*64)
    saved=deepcopy(one.cohorts)
    clock[0]+=timedelta(seconds=5)
    two=EntryExperiment(tmp_path/'two',client=client,clock=lambda:clock[0])
    two.sync()
    assert two.cohorts==saved
    two.enrol([fixture()],capture_sha='b'*64)
    assert two.cohorts==saved
    assert two.screen['reasons']=={'already_frozen_this_session':1}
    assert len([r for r in client.events if r['kind']=='method_enrol'])==1


def test_state_write_failure_never_claims_a_new_observation_or_entry(tmp_path):
    client=Events();w=EntryExperiment(tmp_path/'one',client=client,clock=lambda:NOW)
    client.fail=True
    with pytest.raises(RuntimeError):w.enrol([fixture()],capture_sha='a'*64)
    assert w.cohorts=={}
    assert w.health['quotes_received']==0


def test_worker_keeps_either_active_arm_and_caps_provider_batch(tmp_path,monkeypatch):
    w=EntryExperiment(tmp_path/'one',client=Events(),clock=lambda:NOW)
    c=cohort();w.cohorts={c['setup_id']:c}
    monkeypatch.setattr(w,'outcomes',lambda now:{c['setup_id']:{
        'ask_trigger':{'state':'closed'},'bid_confirmed':{'state':'open'}}})
    assert w.active(NOW)==[c]


def test_quote_events_are_partitioned_and_reconstruct_identical_outcomes(tmp_path):
    client=Events();clock=[NOW]
    w=EntryExperiment(tmp_path/'one',client=client,clock=lambda:clock[0])
    w.enrol([fixture()],capture_sha='a'*64)
    c=next(iter(w.cohorts.values()));entry=D(c['variants'][VARIANT]['plan']['entry_usd'])
    q=quote(c,entry)
    q.pop('durable_received_at')
    clock[0]+=timedelta(seconds=1)
    observer=SimpleNamespace(fetch=lambda selected:([q],[]))
    w.poll(observer)
    assert w.health['quotes_received']==1
    again=EntryExperiment(tmp_path/'two',client=client,clock=lambda:clock[0])
    again.sync()
    assert again.outcomes(clock[0])==w.outcomes(clock[0])
    assert all(r['state']=='open' for r in next(iter(w.outcomes(clock[0]).values())).values())
    assert all(e['experiment_id']==PROTOCOL_ID for e in client.events)


@pytest.mark.parametrize('fault',['price_currency','future_quote','unknown_symbol','changed_cohort'])
def test_corrupted_durable_evidence_is_rejected(tmp_path,fault):
    client=Events();w=EntryExperiment(tmp_path/'one',client=client,clock=lambda:NOW)
    w.enrol([fixture()],capture_sha='a'*64)
    c=next(iter(w.cohorts.values()));entry=D(c['variants'][VARIANT]['plan']['entry_usd'])
    if fault=='changed_cohort':
        p=json.loads(client.events[0]['payload_json']);p['cohort']['variants'][VARIANT]['plan']['stop_usd']='1'
        event=envelope('method_enrol',p,NOW)
    else:
        q=quote(c,entry);q.pop('durable_received_at')
        if fault=='price_currency':q['native_quote_usd']['bid']='1'
        if fault=='future_quote':q['quote']['observed_at']=(NOW+timedelta(seconds=2)).isoformat()
        if fault=='unknown_symbol':q['candidate_id']='stocks:UNKNOWN'
        event=envelope('quote',q,NOW+timedelta(seconds=1))
    client.append(PROTOCOL_ID,[event])
    with pytest.raises(ValueError):w.sync()


def test_report_preserves_unknowns_commissioning_and_entry_cost_arithmetic(tmp_path):
    client=Events();w=EntryExperiment(tmp_path/'one',client=client,clock=lambda:NOW)
    w.enrol([fixture()],capture_sha='a'*64)
    c=next(iter(w.cohorts.values()));p=c['variants'][VARIANT]['plan'];entry=D(p['entry_usd'])
    w.quotes=[quote(c,entry-D('.01'),entry)]
    r=build_report(w,NOW+timedelta(seconds=2))
    assert r['phase']=='commissioning' and r['protocol']['validation_first_day']=='2026-11-16'
    assert r['comparison']['bid_minus_ask_net_eur'] is None
    assert r['rows'][0]['arms']['bid_confirmed']['entry_quality'] is None
    q=r['rows'][0]['arms']['ask_trigger']['entry_quality']
    fill=D(q['simulated_fill_usd'])
    assert D(q['initial_shortfall_pct_stop_distance'])==(fill-D(q['entry_bid_usd']))/(fill-D(p['stop_usd']))*100
    assert q['bid_confirmed_at_entry'] is False
    assert all(v['net_pnl_eur'] is None for v in r['arms'].values())


def test_matched_closed_coverage_gaps_do_not_report_a_complete_comparison(tmp_path):
    w=EntryExperiment(tmp_path/'one',client=Events(),clock=lambda:NOW)
    c=cohort();w.cohorts={c['setup_id']:c};p=c['variants'][VARIANT]['plan']
    w.quotes=[quote(c,D(p['entry_usd'])),quote(c,D(p['target_usd']),seconds=30)]
    r=build_report(w,NOW+timedelta(seconds=31))
    assert r['comparison']['both_closed']==1
    assert r['comparison']['adequate_coverage_pairs']==0
    assert r['comparison']['bid_minus_ask_net_eur'] is None
    assert all(v['closed']==1 for v in r['arms'].values())


def test_fixture_export(tmp_path):
    """Producer contract fixtures are generated by this tested implementation."""
    client=Events();w=EntryExperiment(tmp_path/'one',client=client,clock=lambda:NOW)
    w.enrol([fixture()],capture_sha='a'*64)
    c=next(iter(w.cohorts.values()));p=c['variants'][VARIANT]['plan'];entry=D(p['entry_usd'])
    w.quotes=[quote(c,entry-D('.01'),entry),quote(c,entry,entry+D('.01'),seconds=6),
              quote(c,D(p['target_usd']),seconds=11)]
    report=build_report(w,NOW+timedelta(seconds=12))
    assert report['comparison']['adequate_coverage_pairs']==1
