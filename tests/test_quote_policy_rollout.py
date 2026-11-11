"""Prospective policy, symmetrical uncertainty and immutable historic evidence."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
import os
import subprocess
import sys

import pytest
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.observation_policy import GUARDED, policy_for_day
from market_radar_ai.agents.paper_comparison import ComparisonStore, PROTOCOL, GUARDED_PROTOCOL, protocol_for_day
from market_radar_ai.agents.paper_outcomes import replay_long
from market_radar_ai.agents.paper_tracking import PaperTracker
from market_radar_ai.agents.paper_verdict import finalize
from test_paper_outcomes import q, NOW, plan
from test_conditional_policy_v3 import fixture


def guarded(rows, policy=GUARDED, **kw):
    return replay_long(plan(),rows,decision_at=NOW,entry_expires_at=NOW+timedelta(minutes=5),
        entry_mode='breakout',maximum_entry_spread_bps=Decimal(20),maximum_entry_gap_bps=Decimal(20),
        quote_observation_policy=policy,**kw)


def packet_fixture():
    d,f,n,p,a=fixture()
    p['packet']['quote_observation_policy']=GUARDED
    p['packet_id']=digest(p['packet']);a['packet_id']=p['packet_id']
    for r in a['reviews']:r['packet_id']=p['packet_id']
    return d,f,n,p,a


@pytest.mark.parametrize('bid,ask', [('99.9','110'),('97','100.1')])
def test_wide_preentry_quote_cannot_reject_or_invalidate(bid,ask):
    rows=[q(0,bid,ask),q(1,'100','100.1'),q(2,'102','102.1')]
    assert guarded(rows,policy=None).status=='not_filled'
    new=guarded(rows)
    assert new.status=='closed' and new.entry_at==rows[1].observed_at


@pytest.mark.parametrize('bid,ask', [('97','105'),('102','110')])
def test_wide_exits_are_unknown_for_losses_and_wins(bid,ask):
    rows=[q(0,'100','100'),q(1,bid,ask),q(2,'103','103.1')]
    old=guarded(rows,policy=None);new=guarded(rows)
    assert old.status=='closed' and old.net_pnl_eur is not None
    assert new.status=='unresolved' and new.reason=='exit_quote_quality_unresolved'
    assert new.entry_fill==100 and new.exit_fill is None and new.net_pnl_eur is None


def test_actual_narrow_gap_loss_is_not_hidden():
    r=guarded([q(0,'100','100'),q(1,'97','97.01')])
    assert r.status=='closed' and r.net_pnl_eur==Decimal('-31')


def test_wide_deadline_quote_and_unknown_policy_do_not_invent_fills():
    from market_radar_ai.agents.paper_outcomes import Quote
    r=guarded([q(0,'100','100'),Quote(observed_at=plan().exit_by,bid='100',ask='110')],exit_window_seconds=30)
    assert r.reason=='exit_quote_quality_unresolved' and r.net_pnl_eur is None
    with pytest.raises(ValueError,match='unsupported_quote_observation_policy'):
        guarded([],policy='future')


def test_rollout_is_separate_and_old_hash_remains_fixed():
    assert policy_for_day('2026-11-11') is None and policy_for_day('2026-11-12')==GUARDED
    assert protocol_for_day('2026-11-11')==PROTOCOL
    assert protocol_for_day('2026-11-12')==GUARDED_PROTOCOL
    assert digest(PROTOCOL)=='abfaa5c8b4fd3e76a46dddd142bd4747765b32c0caf2c6122afe9dbff6c7e4e8'
    assert digest(GUARDED_PROTOCOL)=='eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8'


def test_enrolment_review_and_decision_bind_exact_quote_policy(tmp_path):
    d,f,n,p,a=packet_fixture();new=ComparisonStore(tmp_path/'new',protocol=GUARDED_PROTOCOL,dataset_kind='synthetic')
    old=ComparisonStore(tmp_path/'old',dataset_kind='synthetic')
    with pytest.raises(ValueError,match='observation_policy_mismatch'):old.enrol(p,now=n)
    with pytest.raises(ValueError,match='observation_policy_mismatch'):old.begin_review(p,now=n)
    new.enrol(p,now=n);new.begin_review(p,now=n)
    result=finalize(p,a,d,f,now=n)
    assert result['verdict']=='PAPER_WATCH_FOR_ENTRY' and result['quote_observation_policy']==GUARDED
    missing=deepcopy(result);missing.pop('quote_observation_policy')
    with pytest.raises(ValueError,match='invalid_comparison_review_chain'):new.record_review(p,a,missing,now=n)
    new.record_review(p,a,result,now=n)
    assert new.report(now=n)['rows'][0]['ai_reviewed']['state']=='watching'
    with pytest.raises(ValueError):ComparisonStore(tmp_path/'new',protocol=PROTOCOL,dataset_kind='synthetic')
    p['packet'].pop('review_policy_version');p['packet_id']=digest(p['packet'])
    with pytest.raises(ValueError,match='quote_policy_requires_current_review_policy'):finalize(p,a,d,f,now=n)


def test_tracker_keeps_bounded_evidence_and_uncertainty_across_restart(tmp_path):
    from market_radar_ai.agents.paper_outcomes import Quote
    d,f,n,p,a=packet_fixture();decision=finalize(p,a,d,f,now=n)
    t=PaperTracker(tmp_path/'journal');key=t.register(decision);entry=Decimal(decision['plan']['entry_eur'])
    for second in range(1,11):
        at=n+timedelta(seconds=second)
        t.observe_transition(key,Quote(observed_at=at,bid=entry,ask=entry*2),symbol=p['packet']['symbol'],source='fixture',now=at)
    r=t.report(now=at)
    assert r['trades'][0]['state']=='watching' and r['trades'][0]['quote_count']==1
    assert 'Quote-quality review required:' in r['note'] and len(r['note'])<1000
    def observe(second,bid,ask):
        at=n+timedelta(seconds=second)
        return t.observe_transition(key,Quote(observed_at=at,bid=bid,ask=ask),symbol=p['packet']['symbol'],source='fixture',now=at)
    assert observe(11,entry,entry)
    assert observe(12,Decimal(decision['plan']['stop_eur'])-1,entry*2)
    assert not observe(13,decision['plan']['target_eur'],decision['plan']['target_eur'])
    r=PaperTracker(t.path).report(now=n+timedelta(seconds=14))['trades'][0]
    assert r['state']=='unresolved' and r['outcome']['net_pnl_eur'] is None and r['quote_count']==3


@pytest.mark.parametrize('bid,ask',[('97','105'),('106','120')])
def test_execution_unknown_retains_committed_capital(monkeypatch,bid,ask):
    from market_radar_ai.agents import execution_research as ex
    from test_execution_research import body,plan as ep,NOW as at
    monkeypatch.setattr(ex,'SOURCE_PROTOCOL',GUARDED_PROTOCOL)
    b=ex.Book('usd_balance','code_only');b.admit('a',body(),ep(),at)
    b.quote('stocks:AAPL',{'observed_at':at.isoformat(),'bid':'100','ask':'100'},at)
    assert b.rows['a']['state']=='open'
    capital=b.committed()
    b.quote('stocks:AAPL',{'observed_at':at.isoformat(),'bid':bid,'ask':ask},at)
    b.advance(at+timedelta(days=1))
    assert b.rows['a']['state']=='unresolved' and b.rows['a']['pnl'] is None
    assert b.committed()==capital and b.balance==1000


def test_guarded_execution_starts_a_new_bound_series():
    code="from market_radar_ai.agents import execution_research as e; import json; e.validate_source_protocol(); print(json.dumps([e.SOURCE_PROTOCOL_ID,e.PROTOCOL['since'],e.EXPERIMENT]))"
    result=subprocess.run([sys.executable,'-c',code],env={**os.environ,'EXECUTION_SOURCE_VERSION':'guarded-v2'},capture_output=True,text=True,check=True)
    source,since,experiment=json.loads(result.stdout)
    assert source==digest(GUARDED_PROTOCOL) and since=='2026-11-12'
    assert experiment!='530424b310fd4096a2871f1b0ac814cab436a2f47879231c17cff1ed3a251d36'
