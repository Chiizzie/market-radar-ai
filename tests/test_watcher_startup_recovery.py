"""Separate bounded bootstrap from real cadence; never soften lasting outages."""
from unittest.mock import Mock
import pytest
from market_radar_ai.agents.comparison_watcher import run
from market_radar_ai.agents.watcher_diagnostics import record_failure,record_quote_recovery,recovered_quote_gaps
from test_paper_watcher import Clock,ENV
from test_nov11_reliability import healthy_recovery


def worker(tmp_path,startup=20,steady_delay=0):
    c=Clock();comparison=Mock();h={'polls':0,'quotes_received':0,'error_polls':0};comparison.health=h
    comparison.sync.side_effect=lambda:c.sleep(startup)
    def poll():
        h['polls']+=1
        if h['polls']==2:
            h['error_polls']+=1;record_failure(h,'stock_quote_unavailable:TEST:stale_quote',c.now())
        else:
            h['quotes_received']+=1;record_quote_recovery(h,'TEST',c.now())
        if h['polls']==3:c.sleep(steady_delay)
    comparison.poll.side_effect=poll
    result=run(env=ENV,output=tmp_path,duration=100,clock=c.now,monotonic=lambda:c.elapsed,sleep=c.sleep,factory=lambda:comparison)
    return result,comparison


def test_recovered_quote_gap_not_confused_with_initial_history_sync(tmp_path):
    r,c=worker(tmp_path)
    assert r['state']=='completed_with_recovered_quote_gaps' and not r['critical_failure']
    assert r['startup_sync_seconds']==r['first_completed_poll_delay_seconds']==20
    assert r['maximum_poll_gap_seconds']==5 and r['requires_attention']
    assert r['comparison']['failure_counts']=={'stock_quote_unavailable':1}
    assert r['comparison']['maximum_quote_gap_seconds']==5
    c.sync.assert_called_once();c.close.assert_called_once()


def test_actual_delay_during_monitoring_remains_critical(tmp_path):
    r,_=worker(tmp_path,steady_delay=20)
    assert r['critical_failure'] and r['maximum_poll_gap_seconds']>15


def test_startup_deadline_failure_is_named_and_has_no_quotes(tmp_path):
    r,c=worker(tmp_path,startup=101)
    assert r['critical_failure'] and r['quotes_received']==0 and r['polls']==0
    assert r['last_failure']['code']=='comparison_startup_deadline_exceeded'
    c.poll.assert_not_called()


@pytest.mark.parametrize('notification',[0,1])
def test_paper_and_comparison_use_same_recovery_limits(notification):
    h=healthy_recovery();h.update(h.pop('comparison'));h['notification_unconfirmed']=notification
    assert recovered_quote_gaps(h)==(notification==0)


def test_paper_worker_reports_recovery_without_clearing_error_counts(tmp_path,monkeypatch):
    from market_radar_ai.agents import paper_watcher as paper
    c=Clock();calls=[0]
    monkeypatch.setattr(paper.journal,'load',lambda *a,**k:({},None))
    def poll(**kwargs):
        calls[0]+=1;failed=calls[0]==2
        return {'state':{},'active_plans':1,'quotes_received':0 if failed else 1,
                'failures':['stock_quote_unavailable:TEST:stale_quote'] if failed else [],
                'observed_symbols':[] if failed else ['TEST'],'report':{},'notifications':{'unconfirmed':0}}
    monkeypatch.setattr(paper,'poll_once',poll)
    r=paper.run(env=ENV,output=tmp_path,duration=100,clock=c.now,monotonic=lambda:c.elapsed,sleep=c.sleep,observer=Mock())
    assert not r['critical_failure'] and r['requires_attention'] and r['error_polls']==1
    assert r['state']=='completed_with_recovered_quote_gaps' and r['quote_gap_counts']=={'TEST':1}


def test_slow_startup_still_observes_for_the_remaining_worker_window(tmp_path):
    r,c=worker(tmp_path,startup=65)
    assert r['startup_state']=='slow' and r['startup_sync_seconds']==65
    assert r['polls']==7 and r['quotes_received']==6 and r['first_completed_poll_delay_seconds']==65
    assert r['requires_attention'] and not r['critical_failure']
    c.close.assert_called_once()

def test_failed_bootstrap_keeps_its_elapsed_time_and_error(tmp_path):
    c=Clock();comparison=Mock();comparison.health={'polls':0,'quotes_received':0,'error_polls':0}
    def fail():
        c.sleep(30)
        raise RuntimeError('invalid_comparison_event')
    comparison.sync.side_effect=fail
    r=run(env=ENV,output=tmp_path,duration=100,clock=c.now,monotonic=lambda:c.elapsed,sleep=c.sleep,factory=lambda:comparison)
    assert r['startup_state']=='failed' and r['startup_sync_seconds']==30
    assert r['critical_failure'] and r['quotes_received']==0 and r['last_failure']['code']=='invalid_comparison_event'
