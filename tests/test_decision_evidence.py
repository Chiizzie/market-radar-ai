from copy import deepcopy
from datetime import timedelta
import json
from decimal import Decimal

from test_paper_comparison import setup, observe, NOW
from market_radar_ai.agents.decision_evidence import build, bounded, PROTOCOL_ID


def test_same_outcome_comparison_retains_rejected_loser_without_fake_fill(tmp_path,monkeypatch):
    s,key,p,a,d=setup(tmp_path,monkeypatch,verdict='reject',delay=10)
    observe(s,p,2,p['packet']['plan']['entry_eur'])
    observe(s,p,3,Decimal(p['packet']['plan']['stop_eur'])-Decimal('.01'))
    source=s.report(now=NOW+timedelta(seconds=20));original=deepcopy(source)
    r=build(s,source)
    assert source==original and r['population_count']==1
    assert r['arms']['code_only']['selected_outcomes']['losses']==1
    assert r['arms']['independent_chief']['selected_outcomes']['losses']==1
    assert r['arms']['full_team']['not_selected']==1
    assert r['arms']['full_team']['selected_outcomes']['closed']==0
    assert Decimal(r['arms']['full_team']['matched_delta_before_model_cost_eur'])>0
    assert r['arms']['full_team']['matched_delta_after_model_cost_eur'] is None
    assert r['traces'][0]['trace_reason']=='baseline_entry_before_review_decision'
    assert r['comparison_rows'][0]['actual_ai_state']=='no_action'
    assert r['model_calls']==0 and not r['strategy_input'] and not r['trade_authorized']


def test_missing_exit_and_incomplete_review_never_become_zero_profit(tmp_path,monkeypatch):
    s,key,p,a,d=setup(tmp_path,monkeypatch)
    observe(s,p,2,p['packet']['plan']['entry_eur'])
    with s.connection() as db:db.execute('DELETE FROM comparison_reviews')
    r=build(s,s.report(now=NOW+timedelta(minutes=1)))
    assert r['population_count']==1 and r['arms']['independent_chief']['incomplete']==1
    assert r['arms']['code_only']['selected_outcomes']['closed']==0
    assert r['arms']['code_only']['matched_delta_before_model_cost_eur'] is None
    assert r['traces'][0]['trace_reason']=='review_not_completed'


def test_different_prompt_is_traced_but_excluded_from_new_comparison(tmp_path,monkeypatch):
    s,key,p,a,d=setup(tmp_path,monkeypatch)
    with s.connection() as db:
        c=json.loads(db.execute('SELECT payload FROM comparison_cohort').fetchone()[0])
        c['packet']['packet']['prompt_revision']='historical-test-only'
        db.execute('UPDATE comparison_cohort SET payload=?',(json.dumps(c),))
    r=build(s,s.report(now=NOW+timedelta(seconds=10)))
    assert r['source_cohorts']==1 and r['population_count']==0


def test_bounded_export_preserves_aggregate_counts_and_labels_omitted(tmp_path,monkeypatch):
    s,key,p,a,d=setup(tmp_path,monkeypatch)
    r=build(s,s.report(now=NOW+timedelta(seconds=10)))
    r['traces']*=1000
    small=bounded(r)
    assert len(json.dumps(small,separators=(',',':')).encode())<=170000
    assert small['traces_omitted']>0 and small['source_cohorts']==1 and small['protocol_id']==PROTOCOL_ID
