"""Read-only operational checks. Key presence is never an API-credit claim."""
import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from ..agents.candidate_packages import digest
from ..agents.comparison_live import EventClient, envelope
from ..agents.execution_research import PROTOCOL as EXECUTION_PROTOCOL, collect
from ..agents.github_budget import GitHubBudgetStore
from ..agents.paper_comparison import aware
from .api_budget import summarize
from .scanner_operations import GitHubRead, health, EXPERIMENT as HEALTH_EXPERIMENT

PROTOCOL = {'version': 'execution-readiness-v1', 'budget_headroom_microeur': 150000,
            'quote_max_age_seconds': 90, 'source_report_max_age_seconds': 1200}
EXPERIMENT = digest(PROTOCOL)


def get_json(session, url, *, headers):
    with session.get(url, headers=headers, timeout=(5, 12), allow_redirects=False, stream=True) as r:
        if r.status_code != 200: raise ValueError('provider_unavailable')
        raw = bytearray()
        for part in r.iter_content(16384):
            raw.extend(part)
            if len(raw) > 250000: raise ValueError('readiness_response_capacity')
    return json.loads(raw)


def build(*, now, env, client, session=None, budget_store=None, github=None, source_events=(), receipt_clock=None):
    session = session or requests.Session()
    receipt_clock = receipt_clock or (lambda: now)
    local = now.astimezone(ZoneInfo('Europe/Dublin'))
    expected = local.weekday() < 5 and 8 <= local.hour < 23
    checks = []
    def add(key, status, detail, observed=None):
        checks.append({'id': key, 'status': status, 'detail': detail,
                       'observed_at': aware(observed).isoformat() if observed else None})
    add('weekday_window', 'pass' if expected else 'paused',
        'Weekday 08:00–23:00 Europe/Dublin monitoring window.' if expected else 'Outside the weekday monitoring window; this is an explicit verification only.', now)
    add('ai_key_configuration', 'pass' if env.get('AI_KEY_PRESENT') == 'true' else 'blocked',
        'Configured key presence only; provider credit, account entitlement and model availability are not checked.')
    budget = None
    try:
        state, _ = (budget_store or GitHubBudgetStore(env.get('GH_BUDGET_TOKEN'))).load()
        budget = summarize(state, now=now)
        room = min(v['remaining_microeur'] for v in budget['periods'].values())
        add('ai_spending_headroom', 'pass' if room >= 150000 else 'blocked',
            f'Lowest remaining configured ledger allowance: EUR {room / 1000000:.6f}; EUR 0.15 required before an attempt. This is not the OpenAI credit balance.', now)
    except (ValueError, RuntimeError, KeyError, TypeError, requests.RequestException):
        add('ai_spending_headroom', 'unavailable', 'Budget ledger could not be validated; no paid calls attempted.')
    add('paper_observer_configuration', 'blocked' if env.get('WATCHER_ENABLED') == 'false' else 'pass',
        'Paper watcher is disabled.' if env.get('WATCHER_ENABLED') == 'false' else
        'Paper watcher enabled; target five-second observations with bounded 40-stock/30-crypto capacity. Actual coverage requires observations.')
    clock = None
    headers = {'APCA-API-KEY-ID': env.get('ALPACA_API_KEY', ''), 'APCA-API-SECRET-KEY': env.get('ALPACA_API_SECRET', '')}
    try:
        raw = get_json(session, 'https://paper-api.alpaca.markets/v2/clock', headers=headers)
        if type(raw['is_open']) is not bool or abs((aware(raw['timestamp']) - now).total_seconds()) > 120:
            raise ValueError('invalid_market_clock')
        clock = {k: raw[k] for k in ('is_open', 'timestamp', 'next_open', 'next_close')}
        for k in ('next_open', 'next_close'):
            if aware(clock[k]) <= now: raise ValueError('invalid_next_market_time')
        add('market_calendar', 'pass', 'Provider clock and next regular-session boundaries received.', raw['timestamp'])
    except (ValueError, KeyError, TypeError, requests.RequestException):
        clock = None
        add('market_calendar', 'unavailable', 'Provider market clock unavailable or invalid.')
    try:
        q = get_json(session, 'https://data.alpaca.markets/v2/stocks/SPY/quotes/latest?feed=iex', headers=headers)['quote']
        from ..agents.execution_research import dec
        if not 0 < dec(q['bp']) <= dec(q['ap']): raise ValueError('invalid_probe_quote')
        received=aware(receipt_clock())
        age = (received - aware(q['t'])).total_seconds()
        if age < -30: raise ValueError('future_quote')
        current = 0 <= age <= 90
        status = 'pass' if current else 'paused' if clock and not clock['is_open'] else 'unavailable'
        add('reference_quote_probe', status,
            f'SPY IEX reference quote age: {age:.1f} seconds. One-symbol provider check; not broker execution or broad coverage.', q['t'])
    except (ValueError, KeyError, TypeError, ArithmeticError, requests.RequestException):
        add('reference_quote_probe', 'unavailable', 'Reference quote probe unavailable; no synthetic quote substituted.')
    ops = health(github or GitHubRead(env.get('GH_BUDGET_TOKEN')), now=now)
    latest = ops['runs'][0] if ops['runs'] else None
    recent = latest and 0 <= (now - aware(latest['created_at'])).total_seconds() <= 1200
    add('scanner_dispatch', 'paused' if not expected else 'pass' if recent else 'unavailable',
        'External scheduler must dispatch the main workflow; configuration alone does not prove cadence.' if not recent else
        f"Recent scanner dispatch observed; workflow status {latest['status']}, conclusion {latest['conclusion'] or 'pending'}.",
        latest['created_at'] if latest else None)
    jobs = {j['name']: j for j in ops['jobs']}
    required = {'collect', 'review', 'paper-watcher', 'method-shadow', 'account-sync', 'market-context'}
    failed = any(j['conclusion'] in ('failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure') for j in jobs.values())
    add('scanner_jobs', 'unavailable' if ops['source_status'] != 'received' else 'blocked' if failed else
        'pass' if required <= jobs.keys() and all(jobs[k]['conclusion'] == 'success' for k in required) else 'pending',
        'Latest completed workflow job metadata only; skipped or not-yet-run components do not demonstrate readiness.')
    reports = [json.loads(e['payload_json']) for e in source_events if e['kind'] == 'report' and aware(e['occurred_at']) <= now]
    last = max(reports, key=lambda r: r['as_of'], default=None)
    if last and last.get('cohort_count', 0) and 0 <= (now - aware(last['as_of'])).total_seconds() <= 1200:
        h = last.get('observation_health', {})
        observed = h.get('quotes_received', 0) > 0 and h.get('error_polls', 1) == 0 and h.get('maximum_poll_gap_seconds', 999) <= 15
        add('observer_under_load', 'pass' if observed else 'pending',
            'Latest worker observed eligible setups without reported >15-second gaps; between-worker coverage remains separate.' if observed else
            'Eligible setups exist but sustained observer coverage is not demonstrated.', last['as_of'])
    else:
        add('observer_under_load', 'pending', 'No recent populated source cohort proves sustained quote cadence or capacity.')
    receipts = []
    try:
        for n in range(4):
            day = (now - timedelta(days=n)).date().isoformat(); cursor = 0
            for _ in range(100):
                page = client.read(HEALTH_EXPERIMENT, day, cursor)
                if not page['events']: break
                for e in page['events']:
                    if e['seq'] <= cursor: raise ValueError('readiness_cursor')
                    cursor = e['seq']
                    if e['kind'] == 'backup_report': receipts.append(json.loads(e['payload_json']))
                if page['next'] != cursor: raise ValueError('readiness_cursor')
            else: raise ValueError('readiness_page_capacity')
        # Each family has a different deadline. The first natural backup was
        # introduced on Saturday; receipts from rehearsal do not prove Monday.
        for family, zone, minute in [('comparison', 'Europe/Dublin', 22*60+30), ('method', 'America/New_York', 16*60+30)]:
            local_end = now.astimezone(ZoneInfo(zone)); due = local_end.date()
            if local_end.hour*60+local_end.minute < minute: due -= timedelta(days=1)
            while due.weekday() >= 5: due -= timedelta(days=1)
            latest_receipt = max((r for r in receipts if r['family'] == family and r['upload_confirmed']), key=lambda r:r['backup_day'], default=None)
            valid = latest_receipt and latest_receipt['backup_day'] >= due.isoformat() and aware(latest_receipt['expires_at']) > now
            pending = due.isoformat() < '2026-11-09'
            add(f'{family}_recovery', 'pending' if pending else 'pass' if valid else 'unavailable',
                'First natural end-of-session backup is not due yet.' if pending else
                'Durable recovery upload receipt exists; later archive-download recovery is not proved.' if valid else
                'No unexpired recovery upload receipt found for the latest due session.',
                latest_receipt['as_of'] if latest_receipt else None)
    except (ValueError, RuntimeError, KeyError, TypeError):
        add('recovery_receipts', 'unavailable', 'Recovery evidence could not be read completely.')
    add('cost_schedule', 'pass' if now.date().isoformat() < EXECUTION_PROTOCOL['fee_schedule_expires'] else 'blocked',
        'Cost assumptions checked 8 November; new experiment admissions stop when the 30-day schedule snapshot expires.')
    blocked = any(c['status'] in ('blocked', 'unavailable') for c in checks)
    status = 'attention_required' if blocked else 'awaiting_live_evidence' if any(c['status'] == 'pending' for c in checks) else 'checks_passed'
    return {'schema_version': 'execution-readiness-report-v1', 'protocol_id': EXPERIMENT,
        'as_of': now.isoformat(), 'evaluation_day': now.date().isoformat(), 'dataset_kind': 'forward',
        'trade_authorized': False, 'strategy_input': False, 'model_calls': 0,
        'status': status, 'checks': checks, 'market_clock': clock, 'budget': budget,
        'note': 'Read-only probes and recorded metadata. No paid model, order, Telegram or scheduler-dispatch calls. '
        'A passed check does not establish a qualifying strategy, continuous observation coverage or profitability.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('artifacts/execution-research/readiness.json'))
    p.add_argument('--publish', action='store_true')
    args = p.parse_args(); now = datetime.now(UTC)
    client = EventClient(os.environ.get('REVIEW_INGEST_SECRET'))
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as scratch: events = collect(client, now=now, root=scratch)
    report = build(now=now, env=os.environ, client=client, source_events=events, receipt_clock=lambda: datetime.now(UTC))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    if args.publish: client.append(EXPERIMENT, [envelope('readiness_report', report, now)])
    print(json.dumps({'state': 'readiness_recorded' if args.publish else 'readiness_created',
        'status': report['status'], 'checks': {c['id']: c['status'] for c in report['checks']},
        'model_calls': 0, 'trade_authorized': False}))


if __name__ == '__main__': main()
