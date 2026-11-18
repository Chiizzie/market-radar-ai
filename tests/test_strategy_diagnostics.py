"""Read-only explanations must preserve frozen strategy results."""
from copy import deepcopy
import json

from test_strategy_experiment import fixture, NOW, Events
from market_radar_ai.agents.strategy_experiment_live import StrategyExperiment
from market_radar_ai.agents.strategy_diagnostics import build, bounded, input_trace, PROTOCOL_ID
from market_radar_ai.agents.candidate_packages import canonical


def test_diagnostics_publish_separately_and_leave_outcomes_unchanged(tmp_path):
    client=Events();w=StrategyExperiment(tmp_path/'one',client=client,clock=lambda:NOW)
    w.enrol([fixture()],capture_sha='a'*64)
    before=deepcopy(w.cohorts);outcomes=w.outcomes(NOW)
    r=w.close();d=json.loads((w.root/'strategy-diagnostics.json').read_text())
    assert w.cohorts==before and w.outcomes(NOW)==outcomes
    assert r['cohort_count']==d['cohort_count']==1
    assert d['model_calls']==0 and d['strategy_input'] is False
    assert not d['closed_rows']
    audit=[e for e in client.events if e['kind']=='audit']
    assert len(audit)==1 and audit[0]['experiment_id']==PROTOCOL_ID
    assert audit[0]['experiment_id']!=r['protocol_id']
    assert d['variants']['same_time_atr_usd']['states']=={'watching':1}


def test_trace_keeps_observed_spread_and_missing_context():
    source=fixture();r=input_trace(source,NOW)
    assert r['assessment']=='observed_reference_only_no_broker_comparison'
    assert r['bar_count']==20 and float(r['spread_bps'])>0
    source['reference_checks']={}
    assert input_trace(source,NOW)['assessment']=='trace_inputs_incomplete'


def test_missing_native_quote_is_not_an_invented_excursion(tmp_path):
    w=StrategyExperiment(tmp_path/'one',client=Events(),clock=lambda:NOW)
    w.enrol([fixture()],capture_sha='a'*64)
    assert build(w,NOW)['closed_rows']==[]


def test_bounded_report_retains_counts_and_marks_omissions():
    r={'closed_rows':[{'note':'x'*200000}], 'latest_input_trace':[], 'cohort_count':1}
    b=bounded(r)
    assert len(canonical(b).encode())<170000
    assert b['cohort_count']==1 and b['closed_rows_omitted']==1
    assert len(r['closed_rows'])==1
