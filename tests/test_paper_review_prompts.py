import json
from types import SimpleNamespace

import pytest
from test_github_budget import MemoryStore
from test_paper_verdict import NOW, fixture

from market_radar_ai.agents.github_budget import GitHubSpendingLedger
from market_radar_ai.agents.openai_pilot import OpenAIPilot
from market_radar_ai.agents.paper_review_prompts import VERSION, instruction
from market_radar_ai.agents.paper_verdict import STAGES, run_metered


def test_actual_paid_path_uses_distinct_trusted_role_instructions(tmp_path, monkeypatch):
    _, packet, _, _ = fixture(monkeypatch)
    client = OpenAIPilot(api_key='synthetic', ledger=GitHubSpendingLedger(MemoryStore()),
                         eur_per_usd='.9', enabled=True)
    seen = []

    def call(**kwargs):
        prompt = json.loads(kwargs['prompt'])
        stage = prompt['stage']
        assert kwargs['instructions'].startswith(instruction(stage))
        assert prompt['instruction'] == instruction(stage)
        assert prompt['packet'] == packet['packet']
        assert len(prompt['peer_reviews']) == (0 if len(seen) < 6 else len(seen))
        assert 'EUR 20' in kwargs['instructions']
        assert 'untrusted' in kwargs['instructions']
        assert 'non-blocking caveats only' in kwargs['instructions']
        seen.append(stage)
        return SimpleNamespace(data={'verdict': 'APPROVE_PAPER', 'rationale': 'Synthetic only',
                                     'source_ids': ['news:test'], 'concerns': []})

    monkeypatch.setattr(client, 'call', call)
    path = tmp_path / 'review.json'
    run_metered(client, packet, {}, None, path=path, clock=lambda: NOW, enabled=True)
    assert seen == STAGES
    assert len({instruction(stage) for stage in STAGES}) == 8
    assert json.loads(path.read_text())['review_policy_version'] == VERSION
    assert max(len(instruction(s)) for s in STAGES) < 7000


def test_unknown_specialist_cannot_fall_back_to_generic_prompt():
    with pytest.raises(ValueError, match='unknown_paper_review_stage'):
        instruction('invented_role')
