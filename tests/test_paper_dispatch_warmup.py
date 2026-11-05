from datetime import datetime,timezone
import pytest
from market_radar_ai.agents import paper_dispatch as dispatch
from test_scheduled_review import ENV

@pytest.mark.parametrize('stamp,expected', [('2026-11-05T16:09:59+00:00','2026-11-05T16:10:00+00:00'),('2026-03-10T15:09:59+00:00','2026-03-10T15:10:00+00:00')])
def test_warmup_never_qualifies_reserves_or_calls_ai(tmp_path,monkeypatch,stamp,expected):
    def fail(*a,**k):raise AssertionError('warmup reached paid pipeline')
    monkeypatch.setattr(dispatch,'build_packets',fail)
    monkeypatch.setattr(dispatch,'OpenAIPilot',fail)
    r=dispatch.execute({},None,tmp_path/'run',env={**ENV,'SCHEDULED_REVIEW_MODE':'paid','PAPER_FINAL_VERDICTS':'true'},clock=lambda:datetime.fromisoformat(stamp))
    assert r['model_calls']==0 and r['earliest_review_at']==expected


def test_at_boundary_still_requires_free_qualification(tmp_path,monkeypatch):
    def fail(*a,**k):raise AssertionError('unqualified candidate reached AI')
    monkeypatch.setattr(dispatch,'build_packets',lambda *a,**k:{'packets':[],'qualification':{}})
    monkeypatch.setattr(dispatch,'OpenAIPilot',fail)
    r=dispatch.execute({},None,tmp_path/'run',env={**ENV,'SCHEDULED_REVIEW_MODE':'paid','PAPER_FINAL_VERDICTS':'true'},clock=lambda:datetime.fromisoformat('2026-11-05T16:10:00+00:00'))
    assert r['model_calls']==0 and r['state']=='no_qualified_candidate_zero_cost'
