"""Synthetic safety and accounting probes for the read-only evidence report."""
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.execution_research import SOURCE_PROTOCOL_ID
from market_radar_ai.agents.trade_evaluation import _arm_summary, evaluate, markdown, stall_exit
from test_comparison_live import environment

NOW = datetime(2026, 11, 10, 15, tzinfo=UTC)


def row(*, net='-2', exit_seconds=3600):
    outcome = {'entry_at':NOW.isoformat(), 'entry_fill':'100',
               'exit_at':(NOW+timedelta(seconds=exit_seconds)).isoformat(),
               'net_pnl_eur':net, 'reason':'scheduled_exit'}
    arm = {'state':'closed','outcome':outcome,'plan':{'entry_eur':'100','stop_eur':'99',
           'quantity':'4','assumed_round_trip_cost_eur':'1',
           'exit_by':(NOW+timedelta(hours=2)).isoformat()}}
    return {'setup_id':'x','candidate_id':'stocks:TEST','enrolled_at':NOW.isoformat(),
            'decision_at':NOW.isoformat(),'arms':{'code_only':arm,'ai_reviewed':deepcopy(arm)}}


def quote(seconds, bid='100', observed_seconds=None):
    return {'kind':'quote','payload_json':json.dumps({'candidate_id':'stocks:TEST',
        'received_at':(NOW+timedelta(seconds=seconds)).isoformat(),
        'quote':{'observed_at':(NOW+timedelta(seconds=seconds if observed_seconds is None else observed_seconds)).isoformat(),
                 'bid':bid}})}


def full_path():
    return [quote(s) for s in range(0,901,5)]


def test_flat_cost_accounting_does_not_score_unfilled_as_zero():
    a=row(); b=row(net='3'); b['setup_id']='y'
    c=row(); c['arms']['code_only'].update(state='not_filled',outcome={'reason':'no_observed_eligible_fill'})
    report=_arm_summary([a,b,c],'code_only')
    assert report['closed']==2 and report['wins']==1 and report['losses']==1
    assert report['closed_net_eur']=='1' and report['closed_flat_cost_eur']=='2'
    assert report['closed_before_flat_cost_eur']=='3' and report['distinct_closed_symbols']==1
    assert report['entry_quality']['observed_fills']==2
    assert _arm_summary([c],'code_only')['closed_net_eur'] is None


def test_one_fixed_shadow_keeps_original_fill_and_costs():
    s=stall_exit([row()],full_path(),'code_only')
    assert s['paired_count']==1 and s['paired_delta_eur']=='1'
    assert s['rows'][0]['shadow_net_eur']=='-1'
    assert s['rows'][0]['exit_at']==(NOW+timedelta(minutes=15)).isoformat()
    assert s['status']=='retrospective_diagnostic_not_a_strategy_result'


def test_already_exited_and_progressed_baselines_are_retained():
    assert stall_exit([row(exit_seconds=400)],full_path(),'code_only')['states']=={'baseline_exited_before_evaluation':1}
    events=full_path(); events[40]=quote(200,'100.6')
    s=stall_exit([row()],events,'code_only')
    assert s['states']=={'progress_threshold_reached':1} and s['paired_delta_eur'] is None


def test_missing_and_old_deadline_quotes_are_unavailable():
    events=[quote(s) for s in range(0,900,5)]
    assert stall_exit([row()],events,'code_only')['states']=={'missing_evaluation_quote':1}
    events += [quote(900,observed_seconds=895),quote(930,observed_seconds=899)]
    assert stall_exit([row()],events,'code_only')['states']=={'missing_evaluation_quote':1}
    events.append(quote(931))
    assert stall_exit([row()],events,'code_only')['paired_count']==0


def test_receipt_gaps_and_repeated_stale_source_quotes_are_unavailable():
    events=[e for i,e in enumerate(full_path()) if not 50<i<60]
    assert stall_exit([row()],events,'code_only')['states']=={'observation_gap':1}
    # Receipts every 5s do not repair a 35s hole in source observations.
    events=[quote(s,observed_seconds=250 if 250<s<285 else s) for s in range(0,901,5)]
    assert stall_exit([row()],events,'code_only')['states']=={'observation_gap':1}


def test_future_price_does_not_change_shadow_and_unknown_baseline_has_no_delta():
    events=full_path(); original=stall_exit([row()],events,'code_only')
    assert stall_exit([row()],events+[quote(901,'120')],'code_only')==original
    r=row(); r['arms']['code_only']['outcome'].update(exit_at=None,net_pnl_eur=None)
    s=stall_exit([r],events,'code_only')
    assert s['rows'][0]['shadow_net_eur']=='-1' and s['paired_delta_eur'] is None


def test_authenticated_projection_roundtrip_and_input_mismatch(tmp_path, monkeypatch):
    store,packet,_,time,price,client=environment(tmp_path,monkeypatch)
    store.enrol(packet,now=time[0]);time[0]+=timedelta(seconds=1);store.poll()
    price[0]=packet['packet']['plan']['target_eur'];time[0]+=timedelta(seconds=1);store.poll()
    events=client.events
    execution={'schema_version':'execution-research-report-v1','source_protocol_id':SOURCE_PROTOCOL_ID,
        'dataset_kind':'forward','trade_authorized':False,'as_of':time[0].isoformat(),
        'evaluation_day':store.day,'source_sha256':digest(events),'source_events':len(events),
        'books':[],'since':store.day,'source_cohorts':1,'source_last_at':time[0].isoformat(),'costs_verified':False}
    report=evaluate(events,execution)
    from market_radar_ai.agents.event_archive import EventArchive
    with EventArchive() as archive:
        for item in events:archive.append(item)
        assert evaluate(archive,execution)==report
    assert report['cohort_count']==1 and report['arms']['code_only']['closed']==1
    assert report['dataset_kind']=='historical_analysis' and report['trade_authorized'] is False
    assert report['exposure']['code_only']['peak_assumed_concurrent_positions']==1
    assert '1 setups across 1 symbols' in markdown(report)
    before=deepcopy(events)
    evaluate(events,execution)
    assert events==before
    bad=deepcopy(execution);bad['source_sha256']='0'*64
    with pytest.raises(ValueError,match='execution_source_export_mismatch'):evaluate(events,bad)
    bad=deepcopy(execution);bad['dataset_kind']='historical_analysis'
    with pytest.raises(ValueError,match='current_forward_execution_source_required'):evaluate(events,bad)
    tampered=deepcopy(events);tampered[0]['payload_json']='{}'
    bad=deepcopy(execution);bad['source_sha256']=digest(tampered)
    with pytest.raises(ValueError,match='invalid_comparison_event'):evaluate(tampered,bad)
