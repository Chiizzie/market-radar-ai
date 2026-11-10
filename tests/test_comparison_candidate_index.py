from datetime import timedelta
import sqlite3
import pytest
from test_paper_verdict import fixture,NOW
from market_radar_ai.agents.paper_comparison import ComparisonStore
from market_radar_ai.agents.paper_outcomes import Quote


def test_index_reopens_existing_projection_without_changing_evidence(tmp_path,monkeypatch):
    _,packet,_,_=fixture(monkeypatch)
    path=tmp_path/'comparison.sqlite'
    original=ComparisonStore(path,dataset_kind='synthetic')
    original.enrol(packet,now=NOW)
    with sqlite3.connect(path) as db:
        db.execute('DROP INDEX comparison_candidate_enrolment')
        before=db.execute('SELECT id,payload FROM comparison_cohort').fetchall()
    reopened=ComparisonStore(path,dataset_kind='synthetic')
    reopened.observe(packet['packet']['candidate_id'],Quote(observed_at=NOW,bid='10',ask='10'),source='synthetic',received_at=NOW)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT id,payload FROM comparison_cohort').fetchall()==before
        query="SELECT json_extract(payload,'$.enrolled_at') FROM comparison_cohort WHERE json_extract(payload,'$.packet.packet.candidate_id')=?"
        plan=db.execute('EXPLAIN QUERY PLAN '+query,(packet['packet']['candidate_id'],)).fetchall()
        assert any('USING' in row[-1] and 'comparison_candidate_enrolment' in row[-1] for row in plan)


def test_rolled_back_enrolment_never_clears_later_observation(tmp_path,monkeypatch):
    _,packet,_,_=fixture(monkeypatch)
    store=ComparisonStore(tmp_path/'comparison.sqlite',dataset_kind='synthetic')
    with pytest.raises(RuntimeError):
        with store.replay_batch():
            store.enrol(packet,now=NOW)
            store.observe(packet['packet']['candidate_id'],Quote(observed_at=NOW,bid='10',ask='10'),source='synthetic',received_at=NOW)
            raise RuntimeError('rollback')
    with pytest.raises(ValueError,match='observe_only_after_comparison_enrolment'):
        store.observe(packet['packet']['candidate_id'],Quote(observed_at=NOW,bid='10',ask='10'),source='synthetic',received_at=NOW)
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT count(*) FROM comparison_quotes').fetchone()[0]==0


def test_index_preserves_fractional_time_boundary(tmp_path,monkeypatch):
    _,packet,_,_=fixture(monkeypatch)
    enrolled=NOW+timedelta(microseconds=1)
    store=ComparisonStore(tmp_path/'comparison.sqlite',dataset_kind='synthetic')
    store.enrol(packet,now=enrolled)
    with pytest.raises(ValueError,match='observe_only_after_comparison_enrolment'):
        store.observe(packet['packet']['candidate_id'],Quote(observed_at=NOW,bid='10',ask='10'),source='synthetic',received_at=enrolled)
    store.observe(packet['packet']['candidate_id'],Quote(observed_at=enrolled,bid='10',ask='10'),source='synthetic',received_at=enrolled)


def test_index_sees_other_connection_commit_and_preserves_quote_immutability(tmp_path,monkeypatch):
    _,packet,_,_=fixture(monkeypatch)
    path=tmp_path/'comparison.sqlite'
    observer=ComparisonStore(path,dataset_kind='synthetic')
    writer=ComparisonStore(path,dataset_kind='synthetic')
    candidate=packet['packet']['candidate_id']
    quote=Quote(observed_at=NOW,bid='10',ask='10')
    with pytest.raises(ValueError,match='observe_only_after_comparison_enrolment'):
        observer.observe(candidate,quote,source='synthetic',received_at=NOW)
    writer.enrol(packet,now=NOW)
    observer.observe(candidate,quote,source='synthetic',received_at=NOW)
    with pytest.raises(ValueError,match='observe_only_after_comparison_enrolment'):
        observer.observe('stocks:NOT_ENROLLED',quote,source='synthetic',received_at=NOW)
    with pytest.raises(ValueError,match='comparison_observation_is_immutable'):
        observer.observe(candidate,Quote(observed_at=NOW,bid='11',ask='11'),source='synthetic',received_at=NOW)
