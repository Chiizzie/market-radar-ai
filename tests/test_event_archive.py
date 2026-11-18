from datetime import timedelta
import gzip,json
from pathlib import Path
import pytest
from market_radar_ai.agents.event_archive import EventArchive
from market_radar_ai.agents.candidate_packages import canonical,digest
from market_radar_ai.agents.execution_research import replay
from test_execution_research import NOW,enrol,quote,event


def test_disk_and_list_replay_match_exactly_including_original_source_order():
    rows=[quote(3,105,seconds=8),enrol(1),quote(2,100,seconds=1)]
    with EventArchive() as archive:
        for row in rows:archive.append(row)
        assert list(archive)==rows
        assert list(archive.ordered())==sorted(rows,key=lambda x:x['seq'])
        assert archive.source_digest()==digest(rows)
        assert replay(archive,now=NOW+timedelta(minutes=5))==replay(rows,now=NOW+timedelta(minutes=5))


def test_empty_unicode_and_stable_duplicates_preserve_exact_source_hash():
    with EventArchive() as archive:
        assert archive==[] and archive.source_digest()==digest([])
        rows=[{'seq':3,'payload_json':'€ non-ASCII','event_id':'same'}, {'seq':1,'payload_json':'1'}, {'seq':3,'payload_json':'second'}]
        for row in rows:archive.append(row)
        assert archive.source_digest()==digest(rows)
        assert list(archive.ordered())==[rows[1],rows[0],rows[2]]


@pytest.mark.parametrize('kwargs',[{'max_bytes':20},{'max_events':0}])
def test_capacity_failure_does_not_append_or_claim_partial_new_evidence(kwargs):
    with EventArchive(**kwargs) as archive:
        with pytest.raises(ValueError,match='execution_source_capacity'):archive.append({'seq':1,'payload_json':'x'*40})
        assert len(archive)==0 and archive.source_digest()==digest([])


def test_more_than_old_fifty_megabytes_can_be_read_losslessly_without_a_list(tmp_path):
    row={'seq':0,'payload_json':'x'*175000};expected=[]
    with EventArchive() as archive:
        for n in range(300):
            value={**row,'seq':n};archive.append(value)
        assert archive.size_bytes>50_000_000 and len(archive)==300
        assert sum(len(e['payload_json']) for e in archive)==52_500_000
        assert next(archive.ordered())==row
        target=tmp_path/'source.gz'
        with gzip.open(target,'wt') as f:
            for e in archive:f.write(canonical(e)+'\n')
        with EventArchive() as restored:
            with gzip.open(target,'rt') as f:
                for line in f:restored.append(json.loads(line))
            assert restored.source_digest()==archive.source_digest()
            assert len(restored)==len(archive)


def test_close_removes_private_spool():
    archive=EventArchive();folder=Path(archive.directory.name)
    archive.append({'seq':1});assert folder.exists()
    archive.close();archive.close();assert not folder.exists()
    with pytest.raises(ValueError,match='closed'):archive.append({'seq':2})
