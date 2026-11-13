"""Cost/capital sensitivity on immutable prospective evidence; no order/model APIs.

The source cohort still passed the original 40bps gate. This experiment cannot
recover candidates excluded upstream or claim broker-executable fills.
"""
import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from tempfile import TemporaryDirectory

from .candidate_packages import canonical, digest
from .event_archive import EventArchive
from .comparison_live import EventClient, LiveComparison, envelope
from .paper_comparison import PROTOCOL as LEGACY_SOURCE_PROTOCOL, GUARDED_PROTOCOL, aware
from .observation_policy import GUARDED
from .paper_verdict import paper_attempt_id

# Deliberate source binding: changing review policy requires a new experiment,
# never silently repoint an existing portfolio series to another cohort.
SOURCE_VERSION = os.environ.get('EXECUTION_SOURCE_VERSION','legacy')
if SOURCE_VERSION not in ('legacy','guarded-v2'):
    raise ValueError('unsupported_execution_source_version')
SOURCE_PROTOCOL = GUARDED_PROTOCOL if SOURCE_VERSION=='guarded-v2' else LEGACY_SOURCE_PROTOCOL
SOURCE_PROTOCOL_ID = ('eab2d59128f2d320ec2d32e1cd903d2b3d9d17c93f324534c607f640e1b93fd8'
                      if SOURCE_VERSION=='guarded-v2' else
                      'abfaa5c8b4fd3e76a46dddd142bd4747765b32c0caf2c6122afe9dbff6c7e4e8')

def validate_source_protocol():
    if digest(SOURCE_PROTOCOL) != SOURCE_PROTOCOL_ID:
        raise ValueError('execution_source_protocol_mismatch')

D = Decimal
PROFILES = {
    'eur_conversion': {'label': 'EUR conversion on both legs', 'fx_bps': '15', 'slippage_bps': '5'},
    'usd_balance': {'label': 'Existing USD balance, no trade conversion', 'fx_bps': '0', 'slippage_bps': '5'},
    'stressed': {'label': 'EUR conversion, stressed slippage', 'fx_bps': '15', 'slippage_bps': '20'},
}
PROTOCOL = {
    'version': 'execution-research-v2' if SOURCE_VERSION=='guarded-v2' else 'execution-research-v1',
    'source_protocol_id': SOURCE_PROTOCOL_ID,
    'since': '2026-11-12' if SOURCE_VERSION=='guarded-v2' else '2026-11-08',
    'initial_balance_eur': '1000', 'maximum_allocation_eur': '500',
    'maximum_trade_risk_eur': '20', 'maximum_combined_risk_eur': '40', 'maximum_positions': 3,
    'minimum_net_rr': '2', 'maximum_entry_gap_bps': '20', 'maximum_spread_bps': '20',
    'profiles': PROFILES, 'fee_schedule_checked': '2026-11-08', 'fee_schedule_expires': '2026-12-08',
    'sec_sale_rate': '0.0000206', 'finra_usd_per_share': '0.000195',
    'fee_rounding': 'each_component_up_to_eur_cent_assumption',
    'scope': 'stocks_USD_existing_code_qualified_cohort', 'clock': 'durable_receipt_order',
    'exit_window_seconds': 30, 'unknown_overnight_exposure': 'retain_reservation_indefinitely',
}
EXPERIMENT = digest(PROTOCOL)
FEE_SOURCES = ['https://www.trading212.com/terms/invest',
    'https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account']
ACTIVE = {'reserved', 'open', 'unresolved'}


def dec(value):
    x = D(str(value))
    if not x.is_finite() or abs(x) > D('1e12'):
        raise ValueError('invalid_execution_number')
    return x


def money(value):
    return format(value, 'f')


def rounded(value):
    return value.quantize(D('.01'), rounding=ROUND_UP)


def fees(profile, *, entry, exit_price, quantity, fx):
    """Conditional US sale levies; actual broker route/rounding/taxes unverified."""
    f = D(PROFILES[profile]['fx_bps']) / 10000
    return {'entry_fx_eur': rounded(entry * quantity * f),
            'exit_fx_eur': rounded(exit_price * quantity * f),
            'us_sale_levies_eur': rounded(exit_price * quantity * D(PROTOCOL['sec_sale_rate'])
                + quantity * D(PROTOCOL['finra_usd_per_share']) * fx)}


def estimate(profile, plan, *, entry=None, quantity=None):
    slip = D(PROFILES[profile]['slippage_bps']) / 10000
    e = dec(entry) if entry is not None else dec(plan['entry_eur']) * (1 + D('.002')) * (1 + slip)
    q = dec(quantity if quantity is not None else plan['quantity'])
    fx = dec(plan['fx_rate'])
    stop, target = dec(plan['stop_eur']) * (1 - slip), dec(plan['target_eur']) * (1 - slip)
    stop_fees, target_fees = (fees(profile, entry=e, exit_price=x, quantity=q, fx=fx) for x in (stop, target))
    risk = (e - stop) * q + sum(stop_fees.values())
    reward = (target - e) * q - sum(target_fees.values())
    capital = e * q + sum(target_fees.values())
    return {'quantity': q, 'entry': e, 'risk': risk, 'reward': reward, 'capital': capital,
            'rr': reward / risk if risk > 0 else D(0), 'target_fees': target_fees,
            'stop_fees': stop_fees, 'slippage_to_target_eur':
                (e - dec(plan['entry_eur']) + dec(plan['target_eur']) - target) * q}


def size(profile, plan):
    q = min(dec(plan['quantity']), D(500) / dec(plan['entry_eur']))
    # Rounded fees make costs slightly nonlinear. Scale down conservatively;
    # never enlarge the source quantity or alter a structural target/stop.
    for _ in range(12):
        q = q.quantize(D('.000001'), rounding=ROUND_DOWN)
        if q <= 0: raise ValueError('quantity_below_precision')
        e = estimate(profile, plan, quantity=q)
        if e['risk'] <= 20 and e['capital'] <= 500: return e
        q *= min(D(20) / e['risk'], D(500) / e['capital']) * D('.999')
    raise ValueError('cost_sizing_failed')


class Book:
    def __init__(self, profile, arm):
        self.profile, self.arm = profile, arm
        self.balance = D(1000)
        self.rows = {}
        self.peak_capital = self.peak_risk = D(0)

    def committed(self):
        rows = [r for r in self.rows.values() if r['state'] in ACTIVE]
        return sum((r['capital'] for r in rows), D(0)), sum((r['risk'] for r in rows), D(0))

    def advance(self, now):
        for r in self.rows.values():
            if r['state'] == 'reserved' and now >= aware(r['plan']['expires_at']):
                r.update(state='expired', reason='no_observed_eligible_entry')
            elif r['state'] == 'open' and now >= aware(r['plan']['exit_by']):
                r.update(state='unresolved', reason='no_observed_exit_before_cutoff')

    def admit(self, key, body, plan, now):
        if key in self.rows: return
        row = {'setup_id': key, 'candidate_id': body['candidate_id'], 'plan': plan,
            'at': now.isoformat(), 'state': 'blocked', 'reason': None, 'quantity': D(0),
            'capital': D(0), 'risk': D(0), 'reward': None, 'rr': None, 'fees': None,
            'entry_at': None, 'entry_price': None, 'exit_at': None, 'exit_price': None,
            'pnl': None, 'spread_bps': None, 'fee_total': None, 'slippage_cost': None}
        self.rows[key] = row
        if not body['candidate_id'].startswith('stocks:') or plan['native_currency'] != 'USD':
            row['reason'] = 'cost_model_unavailable_for_market'; return
        if not PROTOCOL['fee_schedule_checked'] <= now.date().isoformat() < PROTOCOL['fee_schedule_expires']:
            row['reason'] = 'fee_schedule_stale'; return
        if now >= min(aware(plan['expires_at']), aware(plan['exit_by']) - timedelta(seconds=30)):
            row['reason'] = 'entry_window_expired'; return
        if not 0 < dec(plan['stop_eur']) < dec(plan['entry_eur']) < dec(plan['target_eur']) or dec(plan['fx_rate']) <= 0:
            raise ValueError('invalid_execution_plan')
        e = size(self.profile, plan)
        row.update(quantity=e['quantity'], risk=e['risk'], capital=e['capital'],
                   reward=e['reward'], rr=e['rr'], fees=e['target_fees'])
        if e['rr'] < 2: row['reason'] = 'scenario_net_reward_below_2r'; return
        # The candidate row is still blocked, so it is not included in totals.
        capital, risk = self.committed()
        active = [r for r in self.rows.values() if r['state'] in ACTIVE]
        if any(r['candidate_id'] == row['candidate_id'] for r in active): row['reason'] = 'symbol_already_reserved'
        elif len(active) >= 3: row['reason'] = 'position_limit'
        elif capital + e['capital'] > self.balance: row['reason'] = 'insufficient_shared_capital'
        elif risk + e['risk'] > 40: row['reason'] = 'combined_risk_limit'
        else:
            row.update(state='reserved', reason='awaiting_observed_entry')
            self.peak_capital = max(self.peak_capital, capital + e['capital'])
            self.peak_risk = max(self.peak_risk, risk + e['risk'])

    def quote(self, candidate, quote, now):
        bid, ask = dec(quote['bid']), dec(quote['ask'])
        if not 0 < bid <= ask: raise ValueError('invalid_execution_quote')
        # A durable delay never turns an old exchange observation into a fill.
        if not 0 <= (now - aware(quote['observed_at'])).total_seconds() <= 60: return
        slip = D(PROFILES[self.profile]['slippage_bps']) / 10000
        for r in self.rows.values():
            if r['candidate_id'] != candidate or r['state'] not in {'reserved', 'open'}: continue
            if aware(quote['observed_at']) < aware(r['at']): continue
            p = r['plan']
            spread = (ask - bid) / ((ask + bid) / 2) * 10000
            if SOURCE_PROTOCOL.get('quote_observation_policy')==GUARDED and spread>20:
                if r['state']=='open' and (bid<=dec(p['stop_eur']) or bid>=dec(p['target_eur'])
                        or now>=aware(p['exit_by'])-timedelta(seconds=30)):
                    r.update(state='unresolved',reason='exit_quote_quality_unresolved')
                continue
            if r['state'] == 'reserved':
                if bid <= dec(p['stop_eur']):
                    r.update(state='invalidated', reason='stop_crossed_before_entry'); continue
                if now >= aware(p['exit_by']) - timedelta(seconds=30): continue
                spread = (ask - bid) / ((ask + bid) / 2) * 10000
                if spread > 20 or ask > dec(p['entry_eur']) * D('1.002') or ask < dec(p['entry_eur']): continue
                fill = ask * (1 + slip)
                e = estimate(self.profile, p, entry=fill, quantity=r['quantity'])
                if e['rr'] < 2 or e['risk'] > r['risk'] or e['capital'] > r['capital']: continue
                r.update(state='open', reason='observed_reference_entry', entry_at=now.isoformat(),
                    entry_price=fill, spread_bps=spread, entry_reference=ask)
                continue  # no same-observation entry and exit
            reason = ('scheduled_exit' if now >= aware(p['exit_by']) - timedelta(seconds=30) else
                      'stop' if bid <= dec(p['stop_eur']) else 'target' if bid >= dec(p['target_eur']) else None)
            if reason:
                fill = bid * (1 - slip)
                parts = fees(self.profile, entry=r['entry_price'], exit_price=fill,
                    quantity=r['quantity'], fx=dec(p['fx_rate']))
                fee_total = sum(parts.values())
                pnl = (fill - r['entry_price']) * r['quantity'] - fee_total
                r.update(state='closed', reason=reason, exit_at=now.isoformat(), exit_price=fill,
                    pnl=pnl, fee_total=fee_total, fees=parts,
                    slippage_cost=((r['entry_price'] - r['entry_reference']) + (bid - fill)) * r['quantity'])
                self.balance += pnl

    def report(self):
        capital, risk = self.committed()
        closed = [r for r in self.rows.values() if r['state'] == 'closed']
        counts = dict(sorted(Counter(r['state'] for r in self.rows.values()).items()))
        rows = []
        for r in list(self.rows.values())[-20:]:
            public = {k: r[k] for k in ('setup_id', 'candidate_id', 'state', 'reason', 'entry_at', 'exit_at')}
            public['considered_at'] = r['at']
            for source, target in [('quantity', 'quantity'), ('capital', 'reserved_capital_eur'),
                    ('risk', 'reserved_risk_eur'), ('reward', 'estimated_reward_eur'), ('rr', 'estimated_net_rr'),
                    ('entry_price', 'entry_eur'), ('exit_price', 'exit_eur'), ('pnl', 'net_pnl_eur'),
                    ('spread_bps', 'entry_spread_bps'), ('fee_total', 'closed_fees_eur'), ('slippage_cost', 'closed_slippage_eur')]:
                public[target] = money(r[source]) if r[source] is not None else None
            public['fee_components'] = {k: money(v) for k, v in r['fees'].items()} if r['fees'] else None
            public['original_flat_cost_eur'] = r['plan']['assumed_round_trip_cost_eur']
            rows.append(public)
        return {'profile': self.profile, 'arm': self.arm, 'considered': len(self.rows), 'states': counts,
            'closed': len(closed), 'balance_eur': money(self.balance),
            'reserved_capital_eur': money(capital), 'available_capital_eur': money(self.balance - capital),
            'reserved_risk_eur': money(risk), 'peak_reserved_capital_eur': money(self.peak_capital),
            'peak_reserved_risk_eur': money(self.peak_risk),
            'closed_net_pnl_eur': money(sum((r['pnl'] for r in closed), D(0))) if closed else None,
            'blocked_reasons': dict(sorted(Counter(r['reason'] for r in self.rows.values() if r['state'] == 'blocked').items())),
            'details': rows, 'details_omitted': max(0, len(self.rows) - len(rows))}


def replay(events, *, now, dataset_kind='forward'):
    """Events must first pass LiveComparison's existing identity/chain validator."""
    validate_source_protocol()
    now = aware(now)
    if dataset_kind not in ('forward', 'synthetic'): raise ValueError('invalid_dataset')
    books = [Book(p, a) for p in PROFILES for a in ('code_only', 'ai_reviewed')]
    cohorts, costs, seen = {}, {}, set()
    clock = aware(PROTOCOL['since'] + 'T00:00:00+00:00')
    for event in (events.ordered() if isinstance(events, EventArchive) else sorted(events, key=lambda e: e['seq'])):
        if event['event_id'] in seen: continue
        seen.add(event['event_id'])
        t = max(aware(event['occurred_at']), aware(event['received_at']), clock)
        if t > now: continue
        clock = t
        for book in books: book.advance(t)
        p = json.loads(event['payload_json']); kind = event['kind']
        if kind == 'enrol':
            body = p['packet']['packet']; key = paper_attempt_id(p['packet'], now=aware(body['assembled_at']))
            if key in cohorts: continue
            cohorts[key] = body
            for book in books:
                if book.arm == 'code_only': book.admit(key, body, body['plan'], t)
        elif kind == 'review':
            body = p['packet']['packet']; key = paper_attempt_id(p['packet'], now=aware(body['assembled_at']))
            if key not in cohorts: raise ValueError('review_before_enrolment')
            if p['decision']['verdict'] == 'PAPER_WATCH_FOR_ENTRY':
                for book in books:
                    if book.arm == 'ai_reviewed': book.admit(key, body, p['decision']['plan'], t)
        elif kind == 'quote':
            for book in books: book.quote(p['candidate_id'], p['quote'], t)
        elif kind == 'cost': costs[p['key']] = p
    for book in books: book.advance(now)
    incomplete = sum(k not in costs or not costs[k]['complete'] for k in cohorts)
    result = {'schema_version': 'execution-research-report-v1', 'protocol_id': EXPERIMENT,
        'source_protocol_id': SOURCE_PROTOCOL_ID, 'as_of': now.isoformat(),
        'evaluation_day': now.date().isoformat(), 'since': PROTOCOL['since'], 'dataset_kind': dataset_kind,
        'trade_authorized': False, 'strategy_input': False, 'model_calls': 0,
        'source_events': len(events), 'source_sha256': events.source_digest() if isinstance(events, EventArchive) else digest(events), 'source_cohorts': len(cohorts),
        'source_last_at': max((e['occurred_at'] for e in events), default=None),
        'initial_balance_eur': '1000', 'maximum_trade_risk_eur': '20', 'maximum_combined_risk_eur': '40',
        'maximum_allocation_eur': '500', 'maximum_positions': 3,
        'profiles': PROFILES, 'fee_schedule_checked': PROTOCOL['fee_schedule_checked'],
        'fee_schedule_expires': PROTOCOL['fee_schedule_expires'], 'fee_sources': FEE_SOURCES,
        'costs_verified': False, 'account_currency_route': 'unknown',
        'ai_cost_known_eur': money(sum((D(c['settled_microeur']) / 1000000 for c in costs.values()), D(0))),
        'ai_cost_incomplete_cohorts': incomplete, 'books': [b.report() for b in books],
        'note': 'Six alternative fictional portfolios, each starting with EUR1000; do not add their balances. '
            'Only existing code-qualified source setups are considered: upstream 40bps rejections are absent. '
            'AI approval is reused, not a review of the new cost assumptions. Buy ask/sell bid already embed '
            'the reference spread; it is not charged twice. Slippage, FX routes, fee rounding and US levy '
            'applicability are assumptions, not verified broker costs. Other taxes/ADR charges and sector '
            'correlation are unmodelled. Native-currency scenario excludes earlier/later funding conversions. '
            'AI costs are separate from trading P/L and paper capital. No marked-to-market equity or '
            'profitability claim. Gaps can exceed planned risk; unresolved positions retain their capital '
            'and risk reservations across days. Source watchers may leave observation gaps.'}
    if len(canonical(result).encode()) > 175000: raise ValueError('execution_report_capacity')
    return result


def collect(client, *, now, root, diagnostics=None):
    validate_source_protocol()
    first = aware(PROTOCOL['since'] + 'T00:00:00+00:00').date()
    days = (now.date() - first).days + 1
    if not 1 <= days <= 366: raise ValueError('execution_history_capacity_or_clock')
    events = EventArchive()
    try:
        for n in range(days):
            day = (first + timedelta(days=n)).isoformat()
            worker = LiveComparison(Path(root) / day, client=client, day=day, clock=lambda: now, protocol=SOURCE_PROTOCOL)
            if worker.experiment != SOURCE_PROTOCOL_ID:
                raise ValueError('execution_source_protocol_mismatch')
            worker.sync()  # Existing signed receipt, immutable identity and review validation.
            if diagnostics is not None:
                diagnostics.append({'day':day,**worker.health['initial_sync']})
            path = worker.root / 'comparison-events.jsonl'
            if path.exists():
                with path.open() as source:
                    for line in source:
                        events.append(json.loads(line))
        return events
    except BaseException:
        events.close()
        raise



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('artifacts/execution-research'))
    p.add_argument('--publish', action='store_true')
    args = p.parse_args(); now = datetime.now(UTC)
    client = EventClient(os.environ.get('REVIEW_INGEST_SECRET'))
    source_health=[]
    with TemporaryDirectory() as scratch:
        events = collect(client, now=now, root=scratch, diagnostics=source_health)
    with events:
        now = datetime.now(UTC)  # Include evidence that arrived during the signed reads.
        report = replay(events, now=now)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'source-replay-health.json').write_text(json.dumps({'days':source_health,
            'model_calls':0,'trade_authorized':False},indent=2)+'\n')
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        # A lossless replay artifact accompanies each report. It contains private
        # research evidence, is never included in the viewer report, and expires.
        import gzip
        with gzip.open(args.output / 'source-events.jsonl.gz', 'wt') as out:
            for e in events: out.write(canonical(e) + '\n')
        with EventArchive() as restored:
            with gzip.open(args.output / 'source-events.jsonl.gz', 'rt') as source:
                for line in source: restored.append(json.loads(line))
            if replay(restored, now=now) != report: raise ValueError('execution_restore_mismatch')
        if args.publish: client.append(EXPERIMENT, [envelope('execution_report', report, now)])
        print(json.dumps({'state': 'execution_report_recorded' if args.publish else 'execution_report_created',
            'cohorts': report['source_cohorts'], 'source_events': len(events), 'restore_verified': True,
            'source_replay_seconds':round(sum(d['seconds'] for d in source_health),3),
            'source_projection_seconds':round(sum(d['projection_seconds'] for d in source_health),3),
            'source_bytes':events.size_bytes,
            'model_calls': 0, 'trade_authorized': False}))



if __name__ == '__main__': main()
