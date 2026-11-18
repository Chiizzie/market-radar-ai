"""Concurrency regressions use barriers and injected models, never paid calls."""
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from copy import deepcopy
from datetime import timedelta
from threading import Barrier, Event, Lock
from types import SimpleNamespace

import pytest
from test_github_budget import MemoryStore
from test_paper_verdict import NOW, fixture

from market_radar_ai.agents.github_budget import GitHubSpendingLedger
from market_radar_ai.agents.openai_pilot import OpenAIPilot
from market_radar_ai.agents.paper_verdict import STAGES, review, run_metered


def answer(stage, prompt):
    return {
        'stage': stage, 'packet_id': prompt['packet_id'], 'verdict': 'APPROVE_PAPER',
        'rationale': 'Synthetic concurrency fixture', 'source_ids': ['news:test'],
        'concerns': [], 'reviewed_stages': [r['stage'] for r in prompt['peer_reviews']],
    }


def assessment():
    return {'verdict': 'APPROVE_PAPER', 'rationale': 'Synthetic concurrency fixture',
            'source_ids': ['news:test'], 'concerns': []}


def client():
    return OpenAIPilot(api_key='synthetic', ledger=GitHubSpendingLedger(MemoryStore()),
                       eur_per_usd='.9', enabled=True)


def test_parallel_specialists_are_independent_and_results_keep_stage_order(monkeypatch):
    _, packet, _, _ = fixture(monkeypatch)
    original = deepcopy(packet)
    barrier = Barrier(6, timeout=3)
    completed = [Event() for _ in range(6)]
    finish_order = []
    peer_counts = {}
    lock = Lock()

    def ask(stage, prompt, schema):
        index = STAGES.index(stage)
        if index < 6:
            assert prompt['peer_reviews'] == []
            assert prompt['packet'] == original['packet']
            # One model mutating its supplied object cannot affect another model
            # or the packet that final validation will use.
            if index == 0:
                prompt['packet']['plan']['entry_eur'] = 'synthetic mutation'
            barrier.wait()
            if index != 0:
                assert prompt['packet'] == original['packet']
            if index < 5:
                assert completed[index + 1].wait(3)
            with lock:
                finish_order.append(stage)
            completed[index].set()
        else:
            assert all(event.is_set() for event in completed)
            assert [r['stage'] for r in prompt['peer_reviews']] == STAGES[:index]
            peer_counts[stage] = len(prompt['peer_reviews'])
        return answer(stage, prompt)

    audit = review(packet, {}, None, ask, clock=lambda: NOW, parallel_specialists=True)
    assert finish_order == list(reversed(STAGES[:6]))
    assert [r['stage'] for r in audit['reviews']] == STAGES
    assert peer_counts == {'debate': 6, 'conclusion': 7}
    assert packet == original
    assert audit['model_calls'] == 8 and audit['trade_authorized'] is False


def test_metered_parallel_path_isolates_clients_and_preserves_complete_audit(tmp_path, monkeypatch):
    _, packet, _, _ = fixture(monkeypatch)
    original_client = client()
    barrier = Barrier(6, timeout=3)
    finished = set()
    worker_clients = {}
    request_ids = []
    lock = Lock()

    def call(self, **kwargs):
        prompt = json.loads(kwargs['prompt'])
        stage = prompt['stage']
        index = STAGES.index(stage)
        assert self.ledger is original_client.ledger
        with lock:
            request_ids.append(kwargs['request_id'])
        if index < 6:
            assert prompt['peer_reviews'] == []
            assert self is not original_client
            with lock:
                worker_clients[stage] = self
            self.last_counted_input_tokens = index + 1
            barrier.wait()
            assert self.last_counted_input_tokens == index + 1
            with lock:
                finished.add(stage)
        else:
            assert self is original_client
            assert finished == set(STAGES[:6])
            assert [r['stage'] for r in prompt['peer_reviews']] == STAGES[:index]
        return SimpleNamespace(data=assessment())

    monkeypatch.setattr(OpenAIPilot, 'call', call)
    path = tmp_path / 'review.json'
    audit = run_metered(original_client, packet, {}, None, path=path, clock=lambda: NOW,
                        enabled=True, parallel_specialists=True)
    saved = json.loads(path.read_text())
    assert len({id(c) for c in worker_clients.values()}) == 6
    assert len(set(request_ids)) == 8
    assert all(request_id.startswith('paper-final-v1:' + packet['packet_id'] + ':')
               for request_id in request_ids)
    assert [row['stage'] for row in saved['calls']] == STAGES
    assert all(row['state'] == 'received' and row['assessment'] == assessment()
               for row in saved['calls'])
    assert saved['review_state'] == 'completed'
    assert saved['result'] == audit


def test_failed_specialist_waits_for_inflight_calls_and_preserves_every_audit_row(tmp_path, monkeypatch):
    _, packet, _, _ = fixture(monkeypatch)
    all_started = Event()
    failed = Event()
    release_survivors = Event()
    barrier = Barrier(6, action=all_started.set, timeout=3)
    completed = set()
    lock = Lock()

    def call(self, **kwargs):
        prompt = json.loads(kwargs['prompt'])
        stage = prompt['stage']
        assert stage in STAGES[:6], 'Debate must not run after a specialist fails'
        assert prompt['peer_reviews'] == []
        barrier.wait()
        if stage == STAGES[0]:
            failed.set()
            raise RuntimeError('synthetic specialist failure')
        assert release_survivors.wait(3)
        with lock:
            completed.add(stage)
        return SimpleNamespace(data=assessment())

    monkeypatch.setattr(OpenAIPilot, 'call', call)
    path = tmp_path / 'review.json'
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_metered, client(), packet, {}, None, path=path,
                                 clock=lambda: NOW, enabled=True, parallel_specialists=True)
        try:
            assert all_started.wait(3) and failed.wait(3)
            # The public call must not return while billable work is still in
            # flight, even though the first specialist has already failed.
            with pytest.raises(TimeoutError):
                future.result(timeout=.05)
        finally:
            release_survivors.set()
        with pytest.raises(RuntimeError, match='synthetic specialist failure'):
            future.result(timeout=3)
    assert completed == set(STAGES[1:6])
    saved = json.loads(path.read_text())
    assert [row['stage'] for row in saved['calls']] == STAGES[:6]
    rows = {row['stage']: row for row in saved['calls']}
    assert rows[STAGES[0]]['state'] == 'failed_review'
    assert all(rows[stage]['state'] == 'received' and rows[stage]['assessment'] == assessment()
               for stage in STAGES[1:6])
    assert saved['result'] is None and saved['review_state'] == 'failed'
    assert saved['trade_authorized'] is False


@pytest.mark.parametrize('fault', ['requalification', 'expired_before_start'])
def test_parallel_review_preserves_precall_gate(monkeypatch, fault):
    row, packet, _, _ = fixture(monkeypatch)
    now = NOW
    if fault == 'requalification':
        row['reference_checks']['fx'] = 'UNKNOWN'
    else:
        now += timedelta(minutes=11)
    calls = []

    def ask(*args):
        calls.append(args)
        raise AssertionError('A blocked packet must not reach any specialist')

    with pytest.raises(ValueError, match='paper_packet_'):
        review(packet, {}, None, ask, clock=lambda: now, parallel_specialists=True)
    assert calls == []


def test_deadline_during_parallel_specialists_suppresses_debate(monkeypatch):
    _, packet, _, _ = fixture(monkeypatch)
    current = [NOW]
    finished = []
    lock = Lock()

    def expire():
        current[0] = NOW + timedelta(minutes=11)

    barrier = Barrier(6, action=expire, timeout=3)

    def ask(stage, prompt, schema):
        assert stage in STAGES[:6]
        barrier.wait()
        with lock:
            finished.append(stage)
        return answer(stage, prompt)

    with pytest.raises(ValueError, match='paper_review_deadline'):
        review(packet, {}, None, ask, clock=lambda: current[0], parallel_specialists=True)
    assert set(finished) == set(STAGES[:6])


@pytest.mark.parametrize('setting, expected', [(None, False), ('false', False), ('true', True)])
def test_dispatch_forwards_only_explicit_parallel_opt_in(tmp_path, monkeypatch, setting, expected):
    import market_radar_ai.agents.paper_dispatch as dispatch

    document, feed = {'capture': 'synthetic'}, {'news': 'synthetic'}
    model_client = object()
    constructed, invocations = [], []
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.permitted', lambda *a: True)
    monkeypatch.setattr(dispatch, 'build_packets', lambda *a, **kw: {'packets': [object()]})
    monkeypatch.setattr(dispatch, 'YahooFxProvider', lambda: SimpleNamespace(
        fetch=lambda *a, **kw: SimpleNamespace(eur_per_unit='.9')))

    def make_client(**kwargs):
        constructed.append(kwargs)
        return model_client

    def pipeline(actual_document, actual_feed, **kwargs):
        assert actual_document is document and actual_feed is feed
        invocations.append(kwargs)
        return {'state': 'synthetic_pipeline_complete'}

    monkeypatch.setattr(dispatch, 'OpenAIPilot', make_client)
    monkeypatch.setattr(dispatch, 'run_pipeline', pipeline)
    env = {'PAPER_FINAL_VERDICTS': 'true', 'GH_BUDGET_TOKEN': 'synthetic-token',
           'OPENAI_API_KEY': 'synthetic-key'}
    if setting is not None:
        env['PARALLEL_PAPER_SPECIALISTS'] = setting
    result = dispatch.execute(document, feed, tmp_path/'review', env=env, clock=lambda: NOW)
    assert result == {'state': 'synthetic_pipeline_complete'}
    assert len(constructed) == len(invocations) == 1
    assert constructed[0]['count_input_tokens'] is True
    assert invocations[0]['client'] is model_client
    assert invocations[0]['enabled'] is True
    assert invocations[0]['parallel_specialists'] is expected
