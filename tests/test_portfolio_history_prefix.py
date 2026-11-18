from datetime import timedelta
from unittest.mock import Mock
import pytest
from test_comparison_live import environment
from market_radar_ai.agents.comparison_live import LiveComparison
from market_radar_ai.agents.comparison_checkpoint import save, sync_report_day


def test_report_restore_still_reads_authority_and_preserves_late_events(tmp_path, monkeypatch):
    first, packet, _, clock, _, client = environment(tmp_path, monkeypatch)
    client.secret = 'fixture-secret-'*3
    first.enrol(packet, now=clock[0])
    tomorrow = (clock[0] + timedelta(days=1)).date().isoformat()
    monkeypatch.setenv('REPORT_CLOSED_HISTORY_DIR', str(tmp_path/'closed'))
    monkeypatch.setenv('REPORT_LIVE_PREFIX_DIR', str(tmp_path/'live'))
    initial = LiveComparison(tmp_path/'initial', client=client, clock=lambda:clock[0])
    stats = sync_report_day(initial, tomorrow, write_closed=True)
    assert stats['prefix_state'] == 'miss' and stats['closed_prefix_saved']
    original_cursor = initial.cursor
    clock[0] += timedelta(seconds=1)
    first.poll()
    client.read = Mock(wraps=client.read)
    warm = LiveComparison(tmp_path/'warm', client=client, clock=lambda:clock[0])
    stats = sync_report_day(warm, tomorrow)
    assert stats['prefix_state'] == 'restored' and stats['tail_events'] > 0
    assert 'closed_prefix_saved' not in stats
    assert client.read.call_args_list[0].args[-1] == original_cursor
    cold = LiveComparison(tmp_path/'cold', client=client, clock=lambda:clock[0])
    cold.sync()
    assert (warm.root/'comparison-events.jsonl').read_bytes() == (cold.root/'comparison-events.jsonl').read_bytes()
    assert warm.store.report(now=clock[0]) == cold.store.report(now=clock[0])
    assert save(warm, tmp_path/'live', client.secret)
    current = LiveComparison(tmp_path/'current', client=client, clock=lambda:clock[0])
    assert sync_report_day(current, first.day)['tail_events'] == 0
    client.fail = True
    unavailable = LiveComparison(tmp_path/'unavailable', client=client, clock=lambda:clock[0])
    with pytest.raises(RuntimeError, match='comparison_storage_unavailable'):
        sync_report_day(unavailable, first.day)
