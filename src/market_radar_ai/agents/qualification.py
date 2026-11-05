"""Free deterministic qualification diagnostics; never an AI or order dispatcher."""
from collections import Counter
from datetime import datetime, timezone
from .candidate_packages import build_packages, digest, verify_package
from .combined_input import build_market_evidence
from .candidate_plan import draft
from .setup_checks import reference_checks, technical_checks, validate_paper_plan


def paid_review_gate(record, *, now):
    """Fail closed: the legacy research contract cannot authorize a final verdict.

    Keep this check ahead of budget reservations and all model calls. Removing
    missing-evidence labels alone must never turn research into admission.
    """
    blockers = []
    try:
        package = verify_package(record, now=now)
        blockers.extend(x for x in package.get('missing_evidence', [])
                        if x != 'six_agent_review_not_run')
        if package.get('plan') is None:
            blockers.append('eur_trade_plan_missing')
    except (ValueError, TypeError, KeyError, AttributeError):
        blockers.append('invalid_or_expired_package')
    blockers.append('legacy_research_package_not_a_paper_verdict')
    return {'eligible_for_paid_review': False,
            'blockers': sorted(set(blockers)), 'model_calls': 0,
            'trade_authorized': False}


def qualify(document, feed, *, now):
    from .early_screening import screen
    early = screen(document, now=now)
    batch = build_packages(document, feed, now=now)
    fx = None
    checked = document.get('stock_reference_checks')
    if isinstance(checked, dict) and isinstance(checked.get('payload'), dict):
        if digest(checked['payload']) == checked.get('payload_sha256'):
            fx = checked['payload'].get('fx')
    rows = []
    for record in batch['packages']:
        p = record['package']
        result = paid_review_gate(record, now=now)
        plan = None
        technical = {"state": "UNAVAILABLE"}
        checks = reference_checks(document, symbol=p["symbol"], market=p["market"], now=now)
        try:
            bars = build_market_evidence(document, symbol=p['symbol'],
                                         market_name=p['market'], now=now)
            technical = technical_checks(bars)
            plan = draft(bars, fx, now=now)
            if plan and checks["exit_deadline"]:
                plan["exit_by"] = checks["exit_deadline"]
                plan["expires_at"] = min(datetime.fromisoformat(plan["expires_at"]),
                                          datetime.fromisoformat(plan["exit_by"])).isoformat()
            if plan is None:
                result['blockers'].append('conditional_setup_not_formed')
        except (ValueError, TypeError, KeyError, ArithmeticError):
            result['blockers'].append('paper_plan_inputs_invalid_or_missing')
        if plan is not None:
            result['blockers'] = [x for x in result['blockers'] if x != 'eur_trade_plan_missing']
            result['blockers'].append('paper_costs_and_allocation_are_assumptions')
        risk = validate_paper_plan(plan, now=now, exit_deadline=checks['exit_deadline'])
        if risk['state'] == 'FAIL':
            result['blockers'].extend(risk['failures'])
        rows.append({'current_news_source_ids': [sid for sid in p['news_source_ids'] if sid not in p['context_only_news_ids']],
                     'review_sources': p['sources'],
                     'technical_checks': technical, 'reference_checks': checks, 'paper_risk_check': risk,
                     'candidate_id': p['candidate_id'], 'symbol': p['symbol'],
                     'market': p['market'], 'selection': p['selection'],
                     'conditional_paper_plan': plan, **result})
    from .paper_verdict import paper_gate
    for row in rows:
        row.update(paper_gate(row, now=now))
    market_context = {'stocks': 'SESSION_UNKNOWN', 'crypto': 'CAPTURE_CHECKS_REQUIRED'}
    stocks = [c['requested_symbol'] for c in document.get('captures', []) if c['market']=='stocks']
    if stocks:
        session = reference_checks(document, symbol=stocks[0], market='stocks', now=now)['market_session']
        market_context['stocks'] = ('REGULAR_SESSION_OPEN' if session=='PASS' else
                                    'REGULAR_SESSION_CLOSED_OR_EXIT_WINDOW' if session=='FAIL' else 'SESSION_UNKNOWN')
    counts = Counter(b for r in rows for b in set(r['paper_blockers']))
    return {'schema_version': 'free-qualification-v1', 'evaluated_at': now.isoformat(),
            'early_screening': early, 'selection': batch['selection'], 'candidates': rows, 'market_context': market_context,
            'shortlisted_count': len(rows), 'paid_eligible_count': 0,
            'paper_review_ready_count': sum(r['eligible_for_paper_review'] for r in rows),
            'blocker_counts': dict(sorted(counts.items())),
            'model_calls': 0, 'trade_authorized': False,
            'note': 'Diagnostic only. Conditional plans use fictional capital and assumed costs; no approved trade or paid verdict.'}


def main():
    import argparse, json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(json.loads(args.capture.read_text()), json.loads(args.evidence.read_text()),
                     now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('market_context', 'shortlisted_count', 'paper_review_ready_count', 'paid_eligible_count', 'blocker_counts', 'model_calls')}))


if __name__ == '__main__':
    main()
