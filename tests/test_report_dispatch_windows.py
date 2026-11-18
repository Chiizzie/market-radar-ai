import datetime
import json
import subprocess
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest


@pytest.fixture
def report_window(tmp_path, monkeypatch):
    now = datetime.datetime(2026, 11, 18, 16, 10, tzinfo=datetime.UTC)
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)
    monkeypatch.setattr(datetime, 'datetime', Clock)
    path = tmp_path/'event.json'
    output = tmp_path/'output'
    monkeypatch.setenv('GITHUB_EVENT_PATH', str(path))
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    monkeypatch.setenv('GITHUB_ENV', str(tmp_path/'env'))
    monkeypatch.setenv('GITHUB_REPOSITORY', 'Chiizzie/market-radar-ai')
    def run(family, event, *, age=0, exported=False):
        monkeypatch.setenv('GITHUB_EVENT_NAME', event)
        path.write_text(json.dumps({'workflow_run': {'created_at': (now-datetime.timedelta(minutes=age)).isoformat(),
                                                     'conclusion': 'failure'}}))
        def api(command, **kwargs):
            result = ({'artifacts': [{'name':'manual-portfolio-41','expired':False}]} if exported
                      else {'artifacts':[]}) if command[-1].endswith('/artifacts') else {
                          'workflow_runs':[{'id':41,'updated_at':now.isoformat()}]}
            return SimpleNamespace(stdout=json.dumps(result))
        monkeypatch.setattr(subprocess, 'run', api)
        text = Path('.github/workflows', family+'.yml').read_text()
        assert 'head_repository.full_name == github.repository' in text
        assert 'github.event.workflow_run.run_attempt == 1' in text
        script = text.split("python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        output.write_text('')
        exec(compile(dedent(script), family, 'exec'), {})
        return 'run=true' in output.read_text().splitlines()
    return run


def test_staggered_report_slots_include_partial_parent_and_reject_delayed_runs(report_window):
    assert report_window('execution-research','workflow_run',age=10)
    assert not report_window('manual-portfolio','workflow_run',age=10)
    assert report_window('manual-portfolio','workflow_run',age=5)
    assert not report_window('execution-research','workflow_run',age=5)
    assert not report_window('execution-research','workflow_run',age=25)
    assert not report_window('manual-portfolio','workflow_run',age=20)


def test_genuine_manual_export_suppresses_duplicate_but_empty_success_does_not(report_window):
    assert report_window('manual-portfolio','schedule')
    assert not report_window('manual-portfolio','schedule',exported=True)
    assert not report_window('manual-portfolio','workflow_run',age=5,exported=True)
    assert report_window('manual-portfolio','workflow_dispatch',exported=True)
