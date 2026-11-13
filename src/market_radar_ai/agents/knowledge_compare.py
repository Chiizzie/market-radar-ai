"""Opt-in future paired review using the existing durable AI budget. Never orders."""
import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .candidate_packages import canonical
from .github_budget import GitHubBudgetStore, GitHubSpendingLedger, validate_state
from .knowledge_pair import PROTOCOL, run_pair, validate_pair
from .knowledge_shadow import bounded_json, prepare
from .openai_pilot import MODEL, OpenAIPilot, IncompleteModelResponse


def claim_pair(ledger, pair, library, *, now):
    validate_pair(pair, library, now=now)
    day = now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
    state, _ = ledger.store.load()
    state = validate_state(state)
    markers = ['knowledge-pair-day-v1:'+day, 'knowledge-pair-attempt-v1:'+pair['pair_id']]
    if any(key in state['entries'] for key in markers):
        return False
    for period, cap in state['limits_microeur'].items():
        entries = [e for e in state['entries'].values() if period=='lifetime'
                   or (period=='daily' and e['day']==day) or (period=='monthly' and e['day'][:7]==day[:7])]
        if cap-sum(e['reserved'] if e['actual'] is None else e['actual'] for e in entries) < 150000:
            return False
    ledger.claim_markers(markers, now)
    return True


class MeteredFailure(RuntimeError):
    def __init__(self, usage):
        self.safe_usage = usage
        super().__init__('metered_shadow_call_failed_no_retry')


def metered_ask(client, *, clock=lambda:datetime.now(UTC)):
    if type(client) is not OpenAIPilot or type(client.ledger) is not GitHubSpendingLedger:
        raise ValueError('durable_metered_client_required')
    if MODEL != PROTOCOL['model'] or client.count_input_tokens is not True:
        raise ValueError('paired_model_or_accounting_mismatch')
    def ask(arm, prompt, schema, request_id):
        try:
            result = client.call(prompt=canonical({k:v for k,v in prompt.items() if k!='instruction'}),
                instructions=prompt['instruction'], schema=schema, request_id=request_id, now=clock(),
                max_output_tokens=PROTOCOL['max_output_tokens'], reasoning_effort=PROTOCOL['reasoning_effort'])
        except IncompleteModelResponse as exc:
            raise MeteredFailure({'settled_microeur':exc.estimated_cost_microeur,
                                  'provider_usage':exc.usage_record}) from None
        return {'data':result.data, 'usage':{'response_id':result.response_id,
            'input_tokens':result.input_tokens, 'output_tokens':result.output_tokens,
            'counted_input_tokens':result.counted_input_tokens,
            'settled_microeur':result.estimated_cost_microeur, 'cost_usd':str(result.cost_usd),
            'eur_per_usd':str(result.eur_per_usd)}}
    return ask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--news', type=Path, required=True)
    parser.add_argument('--library', type=Path, default=Path('knowledge/library-20261113.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--paid', action='store_true', help='Explicit opt-in; at most one pair per Dublin day.')
    args = parser.parse_args()
    if not args.paid:
        raise ValueError('explicit_paid_comparison_flag_required_use_knowledge_shadow_for_free_preparation')
    now = datetime.now(UTC)
    capture = bounded_json(args.capture,4_000_000)
    library = bounded_json(args.library,8_000_000)
    prepared = prepare(capture,bounded_json(args.news,2_000_000),library,now=now)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'cohort-inputs.json').write_text(canonical(prepared)+'\n')
    if not prepared['pairs']:
        (args.output/'report.json').write_text(canonical({'state':'no_eligible_pair','model_calls':0,'trade_authorized':False})+'\n')
        return
    # Choose without reading any outcomes. Retain the entire eligible cohort above.
    pair = sorted(prepared['pairs'],key=lambda p:p['pair_id'])[0]
    ledger = GitHubSpendingLedger(GitHubBudgetStore(os.environ['GH_BUDGET_TOKEN']))
    if not claim_pair(ledger,pair,library,now=datetime.now(UTC)):
        (args.output/'report.json').write_text(canonical({'state':'budget_or_daily_attempt_blocked','model_calls':0,'trade_authorized':False})+'\n')
        return
    fx = capture['stock_reference_checks']['payload']['fx']
    client = OpenAIPilot(api_key=os.environ['OPENAI_API_KEY'],ledger=ledger,eur_per_usd=fx['eur_per_unit'],
                         enabled=True,count_input_tokens=True,receipt_directory=args.output/'receipts')
    def save(report):
        tmp = args.output/'report.tmp'
        tmp.write_text(canonical(report)+'\n')
        tmp.replace(args.output/'report.json')
    result = run_pair(pair,library,ask=metered_ask(client),checkpoint=save)
    save(result)
    print(canonical({'state':result['state'],'pair_id':result['pair_id'],'model_calls':result['model_calls'],
                     'trade_authorized':False}))


if __name__ == '__main__':
    main()
