from unittest.mock import Mock
from market_radar_ai.agents.entry_confirmation_live import run_phase


def worker(tmp_path):
    return Mock(root=tmp_path,health={})


def test_enrolment_releases_without_observing_or_sleeping(tmp_path):
    w=worker(tmp_path);observer=Mock(side_effect=AssertionError('observer while holding lock'))
    sleep=Mock(side_effect=AssertionError('sleep while holding lock'))
    run_phase(w,mode='enrol',duration=330,prepare_inputs=lambda:([{'frozen':'source'}],[], 'sha'),
              observer_factory=observer,monotonic=lambda:0,sleep=sleep)
    w.enrol.assert_called_once_with([{'frozen':'source'}],capture_sha='sha',source_failures=[])
    w.poll.assert_not_called();observer.assert_not_called();sleep.assert_not_called()
    w.close.assert_called_once()


def test_independent_observer_cannot_prepare_or_reenrol(tmp_path):
    w=worker(tmp_path);prepare=Mock(side_effect=AssertionError('must never enrol in unlocked observer'))
    time=[0]
    def sleep(seconds):time[0]+=seconds
    observer=object()
    run_phase(w,mode='observe',duration=11,prepare_inputs=prepare,observer_factory=lambda:observer,
              monotonic=lambda:time[0],sleep=sleep)
    prepare.assert_not_called();w.enrol.assert_not_called()
    assert w.poll.call_count==3
    w.poll.assert_called_with(observer);w.close.assert_called_once()


def test_workflow_serializes_only_enrolment():
    from pathlib import Path
    text=Path('.github/workflows/scheduled-scanner.yml').read_text()
    enrol=text.split('  entry-enrol:')[1].split('  entry-confirmation:')[0]
    observe=text.split('  entry-confirmation:')[1]
    assert 'concurrency:' in enrol and 'cancel-in-progress: false' in enrol
    assert 'concurrency:' not in observe and 'needs:' not in observe
    assert '--mode enrol' in enrol and '--mode observe' not in enrol
    assert '--mode observe' in observe and '--duration 330' in observe
    assert 'TRADING212' not in observe and 'OPENAI' not in observe


def test_observer_restart_retains_last_enrolment_screen_without_redating(tmp_path):
    from test_entry_confirmation import NOW,fixture,Events
    from datetime import timedelta
    from market_radar_ai.agents.entry_confirmation_live import EntryExperiment
    events=Events();first=EntryExperiment(tmp_path/'first',client=events,clock=lambda:NOW)
    first.enrol([fixture()],capture_sha='a'*64)
    report=first.close()
    observer=EntryExperiment(tmp_path/'observer',client=events,clock=lambda:NOW+timedelta(seconds=5))
    observer.sync()
    assert observer.screen==report['screen']
    assert observer.close()['screen']==report['screen']
