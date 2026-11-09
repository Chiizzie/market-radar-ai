from copy import deepcopy
from datetime import datetime,UTC,timedelta
import json

import pytest
from market_radar_ai.agents.research_views import exposure,publication,append_publication,public_plan
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.paper_comparison import PROTOCOL
from test_comparison_live import MemoryEvents,environment

NOW=datetime(2026,11,6,20,tzinfo=UTC)


def row(key,start,end,state='closed'):
    p={'currency':'EUR','entry_eur':'100','stop_eur':'98','target_eur':'105','quantity':'5',
       'assumed_round_trip_cost_eur':'2','expires_at':NOW.isoformat(),'exit_by':NOW.isoformat()}
    return {'setup_id':key*64,'candidate_id':'stocks:'+key.upper(),'strategy_id':'test',
      'enrolled_at':(NOW-timedelta(hours=4)).isoformat(),'review_started_at':None,'decision_at':None,
      'decision_blockers':None,'ai_cost':None,'arms':{'code_only':{'state':state,'plan':public_plan(p),
      'observations_available':2,'outcome':{'status':state,'reason':'test','entry_at':start.isoformat(),
      'exit_at':end.isoformat() if end else None,'entry_fill':'100','exit_fill':'105' if end else None,
      'net_pnl_eur':'23' if end else None,'simulated':True}}}}


def test_simultaneous_capital_release_and_unresolved_exposure():
    rows=[row('a',NOW-timedelta(hours=3),NOW-timedelta(hours=2)),
          row('b',NOW-timedelta(hours=2),NOW-timedelta(hours=1)),
          row('c',NOW-timedelta(hours=2,minutes=30),None,'unresolved')]
    r=exposure(rows,'code_only',now=NOW)
    assert r['open_positions']==0 and r['unresolved_positions']==1
    assert r['unresolved_possible_capital_eur']=='502'
    assert r['unresolved_possible_initial_risk_eur']=='12'
    assert r['peak_assumed_concurrent_positions']==2
    assert r['peak_assumed_concurrent_capital_eur']=='1004'
    assert r['peak_assumed_concurrent_initial_risk_eur']=='24'
    assert exposure(rows,'ai_reviewed',now=NOW)['peak_assumed_concurrent_positions']==0
    assert not r['capital_limit_enforced'] and not r['portfolio_return_established']


def test_instant_round_trip_still_needs_capital():
    r=exposure([row('a',NOW,NOW)],'code_only',now=NOW)
    assert r['open_positions']==0 and r['peak_assumed_concurrent_capital_eur']=='502'


def test_open_at_snapshot_is_included_in_simultaneous_capital():
    r=exposure([row('a',NOW,None,'open_simulation'),row('b',NOW,None,'open_simulation')],'code_only',now=NOW)
    assert r['open_positions']==r['peak_assumed_concurrent_positions']==2
    assert r['peak_assumed_concurrent_capital_eur']==r['open_entry_capital_eur']=='1004'


def test_publication_is_isolated_and_complete_summary_is_last(tmp_path,monkeypatch):
    w,p,a,t,price,events=environment(tmp_path,monkeypatch)
    w.enrol(p,now=t[0]);w.close()
    details=[e for e in events.events if e['kind']=='setup_report']
    summary=json.loads(events.events[-1]['payload_json'])
    assert len(details)==1 and events.events[-1]['kind']=='report'
    detail=json.loads(details[0]['payload_json'])
    assert detail['snapshot_id']==summary['details']['snapshot_id']
    assert details[0]['experiment_id']==summary['details']['storage_id']!=w.experiment
    assert not any(k in detail for k in ('sources','packet','inputs','quote','api_key'))
    assert detail['arms']['ai_reviewed']['state']=='not_reviewed'
    assert summary['exposure']['code_only']['watching_positions']==1
    # Explicit v3 admission/review policy starts an isolated prospective cohort.
    assert digest(PROTOCOL)=='abfaa5c8b4fd3e76a46dddd142bd4747765b32c0caf2c6122afe9dbff6c7e4e8'


def test_failed_detail_write_never_publishes_a_complete_report():
    rows=[row('a',NOW-timedelta(minutes=5),None,'open_simulation')]
    report={'schema_version':'paper-comparison-report-v1','protocol_id':'f'*64,'evaluation_day':'2026-11-06',
        'as_of':NOW.isoformat(),'dataset_kind':'forward','trade_authorized':False,'cohort_count':1}
    events=MemoryEvents();events.fail=True
    with pytest.raises(RuntimeError):append_publication(events,'f'*64,report,rows,clock=lambda:NOW)
    assert not events.events
    report['dataset_kind']='synthetic'
    with pytest.raises(ValueError):publication(report,rows)


def test_publication_retries_preserve_identical_event_receipts():
    rows=[row('a',NOW-timedelta(minutes=5),None,'open_simulation')]
    report={'schema_version':'paper-comparison-report-v1','protocol_id':'f'*64,'evaluation_day':'2026-11-06',
        'as_of':NOW.isoformat(),'dataset_kind':'forward','trade_authorized':False,'cohort_count':1}
    events=MemoryEvents()
    append_publication(events,'f'*64,report,rows,clock=lambda:NOW)
    first=deepcopy(events.events)
    append_publication(events,'f'*64,report,rows,clock=lambda:NOW+timedelta(seconds=3))
    assert events.events==first


def test_partial_detail_batch_does_not_advertise_a_complete_snapshot():
    rows=[{**row('a',NOW-timedelta(minutes=5),None,'open_simulation'),'setup_id':format(i,'064x')} for i in range(101)]
    report={'schema_version':'paper-comparison-report-v1','protocol_id':'f'*64,'evaluation_day':'2026-11-06',
        'as_of':NOW.isoformat(),'dataset_kind':'forward','trade_authorized':False,'cohort_count':101}
    class Interrupted(MemoryEvents):
        def append(self,experiment,batch):
            if self.events:raise RuntimeError('interrupted')
            super().append(experiment,batch)
    events=Interrupted()
    with pytest.raises(RuntimeError):append_publication(events,'f'*64,report,rows,clock=lambda:NOW)
    assert len(events.events)==100 and all(e['kind']=='setup_report' for e in events.events)
