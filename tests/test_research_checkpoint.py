"""Offline cache recovery; no network, credentials or financial operations."""
import gzip
import json
from pathlib import Path
import pytest
from market_radar_ai.agents.candidate_packages import canonical
from market_radar_ai.agents.research_checkpoint import ResearchCheckpoint

SECRET = 'offline-checkpoint-test-secret-' * 2


def cached(tmp_path):
    c = ResearchCheckpoint(tmp_path/'cache', experiment='a'*64, day='2026-11-17', secret=SECRET)
    rows = [{'seq':i, 'event_id':str(i), 'experiment_id':'a'*64, 'day':'2026-11-17'} for i in (7,11)]
    journal = tmp_path/'events.jsonl'
    journal.write_text(''.join(canonical(r)+'\n' for r in rows))
    c.save(journal, 11)
    return c, rows


def test_exact_prefix_recovers_gaps_in_global_sequence(tmp_path):
    c, rows = cached(tmp_path); restored=[]
    assert c.restore(restored.append) == 11
    assert restored == rows


@pytest.mark.parametrize('fault', ['header', 'payload', 'truncated', 'wrong_key', 'other_day', 'other_protocol'])
def test_invalid_cache_never_applies_even_one_row(tmp_path, fault):
    c, rows = cached(tmp_path); raw=c.path.read_bytes(); header, body=raw.split(b'\n',1)
    if fault=='header':
        m=json.loads(header);m['metadata']['cursor']=99;raw=json.dumps(m).encode()+b'\n'+body
    elif fault=='payload': raw=header+b'\n'+gzip.compress(b'{}\n')
    elif fault=='truncated':raw=raw[:-10]
    elif fault=='wrong_key':c.key=b'different-key'
    elif fault=='other_day':c.day='2026-11-18'
    elif fault=='other_protocol':c.experiment='b'*64
    c.path.write_bytes(raw);restored=[]
    assert c.restore(restored.append)==0 and restored==[]


def test_authenticated_invalid_domain_evidence_is_not_silently_accepted(tmp_path):
    c, rows = cached(tmp_path)
    def validate(row):raise ValueError('invalid_domain_evidence')
    with pytest.raises(ValueError,match='invalid_domain_evidence'):c.restore(validate)


@pytest.mark.parametrize('fault',['duplicate','order','cursor'])
def test_bad_prefix_boundaries_are_refused(tmp_path,fault):
    c,rows=cached(tmp_path)
    if fault=='duplicate':rows[1]['event_id']=rows[0]['event_id']
    if fault=='order':rows.reverse()
    journal=tmp_path/'bad.jsonl';journal.write_text(''.join(canonical(r)+'\n' for r in rows))
    c.save(journal,99 if fault=='cursor' else 11);restored=[]
    assert c.restore(restored.append)==0 and restored==[]
