"""Observed Telegram acknowledgements and bounded entry-feasibility research.

No human read receipt, portfolio simulation, fills, model calls or broker orders.
"""
import argparse
import json
import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from .candidate_packages import digest, canonical
from .comparison_live import EventClient, LiveComparison, envelope, event_id
from .manual_execution_profile import timing_gate, validate_profile
from .paper_comparison import GUARDED_PROTOCOL, aware
from .paper_verdict import paper_attempt_id

PROTOCOL = {'version': 'manual-alert-evidence-v1', 'since': '2026-11-16',
    'profile_id': '31cb0c3f4bbcd52fe1c4cf62b4b72fc9113d1ef1368befb4b141c9d00b488b5b',
    'source_protocol_id': 'eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8',
    'clock_basis': 'telegram_server_acknowledgement_not_device_receipt',
    'delays_seconds': [60, 180, 300],
    'scope': 'entry_timing_and_price_feasibility_only_no_portfolio_or_fills'}
EXPERIMENT = 'b36797c142938dd01cca74855ab641dd51de6d5889d70aba2b780c2725c7cf8c'
PROFILE_PATH = Path(__file__).resolve().parents[3] / 'config/research/manual-execution-20261113.json'
CLOCK_KEYS = {'schema_version', 'protocol_id', 'source_protocol_id', 'packet_id', 'setup_id',
    'candidate_id', 'plan_sha256', 'decision_at', 'request_started_at', 'acknowledged_at',
    'message_sent_at', 'recorded_at', 'clock_basis', 'device_receipt_observed',
    'dataset_kind', 'trade_authorized'}
STATES = ('eligible_reference_quote_observed', 'invalidated_before_entry',
          'expired_before_response', 'awaiting_response', 'no_eligible_quote_observed',
          'source_review_missing')


def validate_clock(p):
    if not isinstance(p, dict) or set(p) != CLOCK_KEYS:
        raise ValueError('manual_clock_shape')
    if (digest(PROTOCOL) != EXPERIMENT or p['protocol_id'] != EXPERIMENT
            or p['source_protocol_id'] != PROTOCOL['source_protocol_id']
            or p['schema_version'] != 'manual-alert-clock-v1'
            or p['clock_basis'] != PROTOCOL['clock_basis']
            or p['device_receipt_observed'] is not False or p['trade_authorized'] is not False
            or p['dataset_kind'] != 'forward'):
        raise ValueError('manual_clock_scope')
    for key in ('packet_id', 'plan_sha256'):
        if not isinstance(p[key], str) or not re.fullmatch('[a-f0-9]{64}', p[key]):
            raise ValueError('manual_clock_identity')
    if not re.fullmatch(r'paper-final-attempt-v1:[a-f0-9]{64}', p['setup_id']):
        raise ValueError('manual_clock_identity')
    if not re.fullmatch(r'stocks:[A-Z0-9.\-]{1,20}', p['candidate_id']):
        raise ValueError('manual_clock_market')
    decision, start, ack, recorded = (aware(p[k]) for k in
        ('decision_at', 'request_started_at', 'acknowledged_at', 'recorded_at'))
    if not decision <= start <= ack <= recorded or recorded.date().isoformat() < PROTOCOL['since']:
        raise ValueError('manual_clock_order')
    if p['message_sent_at'] is not None:
        sent = aware(p['message_sent_at'])
        if not start - timedelta(seconds=2) <= sent <= ack + timedelta(seconds=2):
            raise ValueError('manual_provider_clock')
    return p


def record_ack(archive, *, request_started_at, acknowledged_at, provider_date, recorded_at, client):
    if aware(recorded_at).date().isoformat() < PROTOCOL['since']:
        return {'state': 'before_manual_validation_start'}
    d = archive['decision']
    if d['verdict'] != 'PAPER_WATCH_FOR_ENTRY' or not d['candidate_id'].startswith('stocks:'):
        return {'state': 'no_stock_watch_clock'}
    if aware(request_started_at) >= aware(d['plan']['expires_at']):
        return {'state': 'expired_watch_not_sent'}
    body = json.loads(archive['packet_json'])
    if digest(body) != archive['packet_id']:
        raise ValueError('manual_packet_hash')
    packet = {'packet': body, 'packet_id': archive['packet_id']}
    # The durable source comparison validates the full packet/review again on read.
    sent = None
    if provider_date is not None:
        if type(provider_date) is not int or provider_date <= 0:
            raise ValueError('manual_provider_clock')
        sent = datetime.fromtimestamp(provider_date, UTC).isoformat()
    p = {'schema_version': 'manual-alert-clock-v1', 'protocol_id': EXPERIMENT,
         'source_protocol_id': PROTOCOL['source_protocol_id'], 'packet_id': archive['packet_id'],
         'setup_id': paper_attempt_id(packet, now=aware(body['assembled_at'])),
         'candidate_id': d['candidate_id'], 'plan_sha256': digest(d['plan']),
         'decision_at': d['evaluated_at'], 'request_started_at': aware(request_started_at).isoformat(),
         'acknowledged_at': aware(acknowledged_at).isoformat(), 'message_sent_at': sent,
         'recorded_at': aware(recorded_at).isoformat(), 'clock_basis': PROTOCOL['clock_basis'],
         'device_receipt_observed': False, 'dataset_kind': 'forward', 'trade_authorized': False}
    validate_clock(p)
    client.append(EXPERIMENT, [envelope('audit', p, recorded_at)])
    return {'state': 'manual_ack_clock_recorded', 'protocol_id': EXPERIMENT,
            'acknowledged_at': p['acknowledged_at'], 'device_receipt_observed': False}


def read_clocks(client, day):
    cursor, clocks, size = 0, [], 0
    for _ in range(100):
        page = client.read(EXPERIMENT, day, cursor)
        if not page['events']:
            return clocks
        for row in page['events']:
            size += len(canonical(row).encode())
            if (size > 5_000_000 or row['experiment_id'] != EXPERIMENT or row['day'] != day
                    or row['kind'] != 'audit' or type(row['seq']) is not int or row['seq'] <= cursor
                    or event_id(EXPERIMENT, row) != row['event_id']):
                raise ValueError('manual_event_identity_or_capacity')
            cursor = row['seq']
            p = json.loads(row['payload_json'])
            if p.get('schema_version') == 'manual-alert-clock-v1':
                validate_clock(p)
                if aware(p['recorded_at']) != aware(row['occurred_at']):
                    raise ValueError('manual_clock_partition')
                clocks.append(row)
            elif p.get('schema_version') != 'manual-alert-audit-v1':
                raise ValueError('unknown_manual_event')
        if page['next'] != cursor:
            raise ValueError('manual_event_cursor')
    raise ValueError('manual_event_capacity')


def evaluate(clocks, source, profile, *, now, source_loaded=True):
    """Source events must first pass LiveComparison's immutable replay validator."""
    validate_profile(profile)
    now = aware(now)
    reviews, quotes, chain_at = {}, {}, aware(PROTOCOL['since']+'T00:00:00+00:00')
    for row in sorted(source, key=lambda r: r['seq']):
        at = max(aware(row['occurred_at']), aware(row['received_at']), chain_at)
        if at > now:
            continue
        chain_at = at
        p = json.loads(row['payload_json'])
        if row['kind'] == 'review' and p['decision']['verdict'] == 'PAPER_WATCH_FOR_ENTRY':
            key = p['packet']['packet_id']
            if key in reviews:
                raise ValueError('duplicate_manual_source_review')
            reviews[key] = (p, at)
        elif row['kind'] == 'quote':
            quotes.setdefault(p['candidate_id'], []).append((p['quote'], at))
    rows, seen = [], set()
    for event in clocks:
        c = validate_clock(json.loads(event['payload_json']))
        if max(aware(c['recorded_at']), aware(event['received_at'])) > now:
            continue
        if c['packet_id'] in seen:
            raise ValueError('duplicate_manual_clock')
        seen.add(c['packet_id'])
        source_review = reviews.get(c['packet_id'])
        details = []
        for delay in PROTOCOL['delays_seconds']:
            state, observed = 'source_review_missing', None
            ready = aware(c['acknowledged_at']) + timedelta(seconds=delay)
            if source_review:
                p, decision_available = source_review
                d, body = p['decision'], p['packet']['packet']
                if (digest(d['plan']) != c['plan_sha256'] or d['candidate_id'] != c['candidate_id']
                        or paper_attempt_id(p['packet'], now=aware(body['assembled_at'])) != c['setup_id']
                        or aware(d['evaluated_at']) != aware(c['decision_at'])):
                    raise ValueError('manual_clock_review_binding')
                plan = d['plan']
                # Evidence cannot become available before its durable receipt.
                available = max(decision_available, aware(event['received_at']))
                ready = max(ready, available)
                deadline = min(aware(plan['expires_at']), aware(plan['exit_by']) - timedelta(seconds=30))
                state = ('expired_before_response' if ready >= deadline else
                         'awaiting_response' if now < ready else 'no_eligible_quote_observed')
                if state == 'no_eligible_quote_observed':
                    for quote, at in quotes.get(c['candidate_id'], []):
                        qt = aware(quote['observed_at'])
                        if at < available or at >= deadline or qt < aware(c['acknowledged_at']):
                            continue
                        bid, ask = Decimal(quote['bid']), Decimal(quote['ask'])
                        if not 0 < bid <= ask or not 0 <= (at-qt).total_seconds() <= 60:
                            continue
                        if (ask-bid)/((ask+bid)/2)*10000 > 20:
                            continue
                        if bid <= Decimal(plan['stop_eur']):
                            state = 'invalidated_before_entry'; break
                        gate = timing_gate(profile, delay_seconds=delay, as_of=at,
                            alert_received_at=c['acknowledged_at'], decision_available_at=available,
                            quote_observed_at=qt, quote_received_at=at,
                            expires_at=plan['expires_at'], exit_by=plan['exit_by'], session_permitted=True)
                        if (gate['status'] == 'profile_checks_passed'
                                and Decimal(plan['entry_eur']) <= ask <= Decimal(plan['entry_eur'])*Decimal('1.002')):
                            state, observed = 'eligible_reference_quote_observed', at.isoformat(); break
            details.append({'delay_seconds': delay, 'state': state, 'ready_at': ready.isoformat(),
                            'first_eligible_quote_at': observed})
        rows.append({'packet_id': c['packet_id'], 'setup_id': c['setup_id'],
                     'candidate_id': c['candidate_id'], 'acknowledged_at': c['acknowledged_at'],
                     'scenarios': details})
    summary = [{ 'delay_seconds': delay,
                 'states': {s: sum(r['scenarios'][i]['state'] == s for r in rows) for s in STATES}}
               for i, delay in enumerate(PROTOCOL['delays_seconds'])]
    return {'schema_version': 'manual-alert-audit-v1', 'protocol_id': EXPERIMENT,
            'profile_id': PROTOCOL['profile_id'], 'as_of': now.isoformat(),
            'evaluation_day': now.date().isoformat(), 'dataset_kind': 'forward',
            'trade_authorized': False, 'strategy_input': False, 'model_calls': 0,
            'state': 'before_validation_start' if now.date().isoformat() < PROTOCOL['since'] else
                     'evaluated' if rows else 'no_confirmed_alert_clocks',
            'clock_basis': PROTOCOL['clock_basis'], 'device_receipt_observed': False,
            'source_events': len(source), 'source_sha256': digest(source), 'source_loaded': source_loaded,
            'clocks': len(rows), 'unmatched_clocks': sum(r['scenarios'][0]['state']=='source_review_missing' for r in rows),
            'approved_reviews_without_clock': len(set(reviews)-seen) if source_loaded else None, 'summary': summary,
            'details': rows[-50:], 'details_omitted': max(0, len(rows)-50),
            'portfolio_evaluated': False, 'costs_verified': False, 'broker_executable': False,
            'note': 'Response delays are assumptions from Telegram server acknowledgement, not measured user reads. '
                    'Session timing uses the approved plan window, not a new exchange or halt check. '
                    'This tests reference-quote timing and trigger feasibility only; no fills, portfolio P/L or broker-cost validation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/manual-alert-evidence'))
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    now = datetime.now(UTC)
    profile = validate_profile(json.loads(PROFILE_PATH.read_text()))
    client = EventClient(os.environ.get('REVIEW_INGEST_SECRET'))
    day = now.date().isoformat()
    clocks = read_clocks(client, day) if day >= PROTOCOL['since'] else []
    source = []
    if clocks:
        with TemporaryDirectory() as directory:
            worker = LiveComparison(directory, client=client, day=day, clock=lambda: now, protocol=GUARDED_PROTOCOL)
            if worker.experiment != PROTOCOL['source_protocol_id']:
                raise ValueError('manual_source_protocol')
            worker.sync()
            path = Path(directory)/'comparison-events.jsonl'
            if path.exists():
                if path.stat().st_size > 50_000_000:
                    raise ValueError('manual_source_capacity')
                source = [json.loads(line) for line in path.read_text().splitlines()]
    report = evaluate(clocks, source, profile, now=datetime.now(UTC), source_loaded=bool(clocks))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    if args.publish:
        client.append(EXPERIMENT, [envelope('audit', report, report['as_of'])])
    print(json.dumps({'state': report['state'], 'published': args.publish, 'clocks': report['clocks'],
                      'model_calls': 0, 'trade_authorized': False}))


if __name__ == '__main__':
    main()
