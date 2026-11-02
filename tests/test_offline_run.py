import json
from market_radar_ai.agents.offline_run import run_offline


def test_supported_run_to_report_and_repeat(tmp_path):
    first=run_offline(tmp_path,'supported')
    assert first['mock_requests_this_invocation']==7
    assert first['report']['paper_outcome']['net_pnl_eur']=='19'
    assert first['report']['symbol']=='FICTIONAL'
    assert json.loads(open(first['report_path']).read())==first['report']
    again=run_offline(tmp_path,'supported')
    assert again['mock_requests_this_invocation']==0 and again['report']==first['report']


def test_objection_run_to_report_without_fill(tmp_path):
    result=run_offline(tmp_path,'objection')
    assert result['mock_requests_this_invocation']==8
    assert result['report']['accepted_plan'] is None
    assert result['report']['paper_outcome'] is None
    assert result['report']['decision']['unresolved_ids']==['O1']
    assert result['summary']['net_pnl_eur'] is None
