"""Concurrency regressions with mocked storage and provider transport only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from threading import Barrier, Lock
from time import sleep
from types import SimpleNamespace

import pytest

from market_radar_ai.agents.github_budget import GitHubSpendingLedger, initial_state, validate_state
from market_radar_ai.agents.openai_pilot import MODEL, OpenAIPilot

NOW = datetime(2026, 11, 6, 14, tzinfo=UTC)
SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}}


class ConcurrentStore:
    """Each operation is atomic, but an unguarded load/save pair can conflict."""
    def __init__(self):
        self.state = initial_state()
        self.version = 0
        self.lock = Lock()

    def load(self):
        with self.lock:
            result = deepcopy(self.state), self.version
        sleep(0.002)  # Simulated I/O allows competing unguarded transactions to load.
        return result

    def save(self, state, expected_sha):
        sleep(0.002)
        with self.lock:
            if expected_sha != self.version:
                raise RuntimeError('compare_and_swap_conflict')
            self.state = deepcopy(validate_state(state))
            self.version += 1


def parallel(function, count=6):
    start = Barrier(count)

    def invoke(index):
        start.wait(timeout=3)
        return function(index)

    with ThreadPoolExecutor(max_workers=count) as executor:
        return list(executor.map(invoke, range(count)))


def test_parallel_reservations_and_settlements_keep_every_record():
    storage = ConcurrentStore()
    ledger = GitHubSpendingLedger(storage)
    parallel(lambda i: ledger.reserve(f'role-{i}', 10000, NOW))
    assert len(storage.state['entries']) == storage.version == 6
    parallel(lambda i: ledger.settle(f'role-{i}', 100+i))
    assert storage.version == 12
    assert {key: value['actual'] for key, value in storage.state['entries'].items()} == {
        f'role-{i}': 100+i for i in range(6)}
    assert ledger.summary()['held_microeur'] == 0
    assert ledger.summary()['settled_microeur'] == 615


def test_parallel_reservations_cannot_exceed_daily_budget():
    storage = ConcurrentStore()
    ledger = GitHubSpendingLedger(storage)

    def reserve(index):
        try:
            ledger.reserve(f'role-{index}', 300000, NOW)
            return 'reserved'
        except RuntimeError as error:
            return str(error)

    results = parallel(reserve)
    assert results.count('reserved') == 3
    assert results.count('daily_spending_limit') == 3
    assert len(storage.state['entries']) == storage.version == 3
    assert ledger.summary()['held_microeur'] == 900000


def test_parallel_duplicate_identity_is_reserved_once():
    storage = ConcurrentStore()
    ledger = GitHubSpendingLedger(storage)

    def reserve(_):
        try:
            ledger.reserve('same-role', 10000, NOW)
            return True
        except ValueError as error:
            assert 'already reserved' in str(error)
            return False

    assert parallel(reserve).count(True) == 1
    assert storage.version == 1


def test_forks_isolate_token_counts_and_allow_parallel_generation(monkeypatch):
    storage = ConcurrentStore()
    ledger = GitHubSpendingLedger(storage)
    original = OpenAIPilot(api_key='fixture', ledger=ledger, eur_per_usd='0.92',
                          enabled=True, count_input_tokens=True)
    original.last_counted_input_tokens = 999
    forks = [original.fork() for _ in range(6)]
    assert all(type(client) is OpenAIPilot and client.ledger is ledger
               and client.rate == Decimal('0.92') and client.count_input_tokens
               and client.last_counted_input_tokens is None for client in forks)
    generation = Barrier(6)

    def post(url, **kwargs):
        index = int(kwargs['json']['input'])
        tokens = 1000+index
        if url.endswith('/input_tokens'):
            data = {'object': 'response.input_tokens', 'input_tokens': tokens}
        else:
            # All six generation calls must overlap; serializing provider I/O
            # with the budget lock would break this barrier rather than pass.
            generation.wait(timeout=3)
            data = {'id': f'response-{index}', 'model': MODEL, 'status': 'completed',
                    'usage': {'input_tokens': tokens, 'output_tokens': 10},
                    'output': [{'type': 'message', 'content': [
                        {'type': 'output_text', 'text': '{"ok":true}'}]}]}
        return SimpleNamespace(status_code=200, json=lambda: data)

    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post', post)
    replies = parallel(lambda i: forks[i].call(prompt=str(i), schema=SCHEMA,
                       request_id=f'role-{i}', now=NOW, max_output_tokens=16))
    assert [reply.counted_input_tokens for reply in replies] == list(range(1000, 1006))
    assert [client.last_counted_input_tokens for client in forks] == list(range(1000, 1006))
    assert original.last_counted_input_tokens == 999
    assert len(storage.state['entries']) == 6 and storage.version == 12
    assert all(row['actual'] is not None and row['usage']['response_id'].startswith('response-')
               for row in storage.state['entries'].values())


def test_fork_ambiguous_reservation_never_generates_or_retries(monkeypatch):
    class LostAcknowledgement(ConcurrentStore):
        def save(self, state, expected_sha):
            super().save(state, expected_sha)
            raise RuntimeError('acknowledgement_lost')

    storage = LostAcknowledgement()
    original = OpenAIPilot(api_key='fixture', ledger=GitHubSpendingLedger(storage),
                          eur_per_usd=1, enabled=True)

    def forbidden(*args, **kwargs):
        pytest.fail('No generation after an unconfirmed reservation')

    monkeypatch.setattr('market_radar_ai.agents.openai_pilot.requests.post', forbidden)
    with pytest.raises(RuntimeError, match='acknowledgement_lost'):
        original.fork().call(prompt='test', schema=SCHEMA, request_id='role', now=NOW)
    with pytest.raises(ValueError, match='already reserved'):
        original.fork().call(prompt='test', schema=SCHEMA, request_id='role', now=NOW)
    assert storage.version == 1 and storage.state['entries']['role']['actual'] is None
