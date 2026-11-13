"""Validate curated research and offline comparison inputs without external services."""
import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tests'))
from test_strategy_routing import (pullback_input, method_input, opening_input, opening_continuation_input,
                                  mean_input, rehash, shifted, competitor_fixture, METHOD_NOW)
from market_radar_ai.agents.candidate_packages import canonical
from market_radar_ai.agents.external_research import ResearchBank, prepare_comparison, validate_comparison, PAIR_PROTOCOL_ID
from market_radar_ai.agents.research_validation import audit_library, audit_future_dependence
from market_radar_ai.agents.strategy_knowledge import Retriever
from market_radar_ai.agents.strategy_registry import ALL, OFFLINE, evaluate
from market_radar_ai.agents.strategy_pair import prepare
from market_radar_ai.agents.paper_comparison import aware


def verify(bank, library):
    research = ResearchBank(bank); cases = Retriever(library); checks = []
    fixtures = {'trend_pullback_reclaim_v1': pullback_input, 'trend_continuation_20bar_v1': pullback_input,
                'opening_continuation_30m_v1': opening_continuation_input, 'opening_range_15m_shadow_v1': opening_input,
                'session_open_avwap_reclaim_v1': method_input, OFFLINE: mean_input,
                'competitor_strength_breakout_shadow_v1': lambda: (rehash(shifted(competitor_fixture())), METHOD_NOW+timedelta(days=10))}
    for strategy in ALL:
        source, now = fixtures[strategy](); result = evaluate(source, strategy, now=now)
        assert result['eligible'], strategy
        extract = research.retrieve(strategy, as_of=now)
        row = {'strategy_id': strategy, 'notes': [n['note_id'] for n in extract['notes']],
               'extract_bytes': len(canonical(extract).encode()), 'offline_only': strategy == OFFLINE}
        if strategy != OFFLINE:
            pair = prepare(result, source, cases, now=now)
            comparison = prepare_comparison(pair, research, cases, now=now)
            validate_comparison(comparison, pair, research, cases, now=now)
            row.update(comparison_id=comparison['comparison_id'], comparison_state='prepared_and_validated_not_run')
        checks.append(row)
    rows = [{'event_id': str(i), 'event_at': f'2026-11-13T15:0{i}:00Z',
             'available_at': f'2026-11-13T15:0{i}:01Z', 'value': v} for i, v in enumerate([100, 101, 102, 10000])]
    def causal(data, at):
        values = [r['value'] for r in data if aware(r['event_at']) <= at and aware(r['available_at']) <= at]
        return sum(values)/len(values)
    leaky = lambda data, at: sum(r['value'] for r in data)/len(data)
    positive = audit_future_dependence(causal, rows, ['2026-11-13T15:02:01Z'])
    negative = audit_future_dependence(leaky, rows, ['2026-11-13T15:02:01Z'])
    assert positive['passed_tested_cutoffs'] == 1 and negative['failed_cutoffs'] == 1
    return {'schema_version': 'external-research-offline-receipt-v1', 'verified_at': datetime.now(UTC).isoformat(),
            'bank_id': bank['bank_id'], 'comparison_protocol_id': PAIR_PROTOCOL_ID,
            'sources_catalogued': len(bank['sources']), 'curated_notes': len(bank['notes']), 'strategy_checks': checks,
            'library_audit': audit_library(library), 'future_dependence_controls': {'causal': positive, 'deliberately_leaky': negative},
            'fixture_kind': 'synthetic_inputs_not_forward_decisions', 'model_calls': 0, 'paid_ai_cost_eur': '0',
            'external_packages_installed': [], 'production_runtime_changed': False, 'trade_authorized': False,
            'performance_claim': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(json.loads((ROOT/'knowledge/external-research-20261113.json').read_text()),
                    json.loads((ROOT/'knowledge/strategy-library-20261113.json').read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(result)+'\n')
    print(canonical(result))


if __name__ == '__main__': main()
