from datetime import datetime
import pytest
from market_radar_ai.agents import paper_dispatch as dispatch
from test_scheduled_review import ENV

@pytest.mark.parametrize('stamp', ['2026-11-05T08:05:00+00:00','2026-11-05T14:59:59+00:00','2026-11-05T15:00:00+00:00','2026-03-10T14:00:00+00:00'])
def test_market_specific_free_qualification_precedes_any_cost(tmp_path,monkeypatch,stamp):
    def fail(*a,**k):raise AssertionError('unqualified candidate reached AI or FX')
    seen=[]
    def build(*a,**k):
        seen.append(k['now']);return {'packets':[],'qualification':{}}
    monkeypatch.setattr(dispatch,'build_packets',build)
    monkeypatch.setattr(dispatch,'OpenAIPilot',fail)
    monkeypatch.setattr(dispatch,'YahooFxProvider',fail)
    r=dispatch.execute({},None,tmp_path/'run',env={**ENV,'SCHEDULED_REVIEW_MODE':'paid','PAPER_FINAL_VERDICTS':'true'},clock=lambda:datetime.fromisoformat(stamp))
    assert len(seen)==1 and r['model_calls']==0 and r['state']=='no_qualified_candidate_zero_cost'

def test_disabled_watcher_stops_paid_work_before_fx_or_models(tmp_path,monkeypatch):
    monkeypatch.setattr(dispatch,'build_packets',lambda *a,**k:{'packets':[{}]})
    def forbidden(*a,**kw):raise AssertionError('Disabled watcher reached paid work')
    monkeypatch.setattr(dispatch,'YahooFxProvider',forbidden)
    result=dispatch.execute({},None,tmp_path/'run',env={**ENV,'SCHEDULED_REVIEW_MODE':'paid',
        'PAPER_FINAL_VERDICTS':'true','PAPER_WATCHER_ENABLED':'false'},clock=lambda:datetime.fromisoformat('2026-11-06T16:00:00+00:00'))
    assert result['model_calls']==0 and result['state']=='paper_watcher_disabled_zero_cost'
