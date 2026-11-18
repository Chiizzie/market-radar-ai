"""Prevent main from again omitting modules called by its production workflows."""
import importlib.util
from pathlib import Path
import re


def test_all_declared_market_radar_workflow_entry_points_are_shipped():
    modules = set()
    for path in Path('.github/workflows').glob('*.yml'):
        modules.update(re.findall(r'python\s+-m\s+(market_radar_ai\.[A-Za-z0-9_.]+)', path.read_text()))
    assert len(modules) > 20
    missing = sorted(module for module in modules if importlib.util.find_spec(module) is None)
    assert missing == []
