"""Shared-capital manual paper replay. No model, notification or order client.

The authoritative state is reconstructed from signed immutable source events.
Every run exports its complete ledger and lossless inputs, then replays them
again before publishing a bounded report. Reports never authorize execution.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .candidate_packages import canonical, digest
from .comparison_live import EventClient, LiveComparison, envelope, event_id
from .event_archive import EventArchive
from .execution_research import Book, PROFILES, PROTOCOL as COST_PROTOCOL, estimate, fees, dec, money
from .manual_alert_evidence import (EXPERIMENT as CLOCK_ID, PROTOCOL as CLOCK_PROTOCOL,
    PROFILE_PATH, read_clocks, validate_clock)
from .manual_execution_profile import validate_profile, risk_gate, timing_gate, ZONE
from .paper_comparison import GUARDED_PROTOCOL, aware
from .paper_verdict import paper_attempt_id

D = Decimal
ACTIVE = {'reserved', 'open', 'unresolved'}
COST_MODEL = {'profiles': deepcopy(PROFILES), 'sec_sale_rate': '0.0000206',
    'finra_usd_per_share': '0.000195', 'fee_schedule_checked': '2026-11-08',
    'fee_schedule_expires': '2026-12-08', 'public_schedule_rechecked': '2026-11-14',
    'rounding': 'each_component_up_to_eur_cent_assumption',
    'actual_costs_verified': False}
PROTOCOL = {'version': 'manual-shared-portfolio-v1', 'since': '2026-11-16',
    'profile_id': CLOCK_PROTOCOL['profile_id'], 'clock_protocol_id': CLOCK_ID,
    'source_protocol_id': CLOCK_PROTOCOL['source_protocol_id'],
    'response_delays_seconds': [60, 180, 300], 'primary_scenario': 'eur_conversion:300',
    'clock_basis': CLOCK_PROTOCOL['clock_basis'], 'risk_timezone': 'Europe/Dublin',
    'cost_model': COST_MODEL, 'minimum_net_rr': '2',
    'maximum_spread_bps': '20', 'maximum_entry_gap_bps': '20',
    'maximum_open_quote_gap_seconds': 60,
    'reservation_policy': 'at_durable_alert_and_review_availability_before_manual_response',
    'sizing': 'source_quantity_may_only_decrease_to_20_eur_risk_and_500_eur_allocation',
    'risk_policy': 'realized_daily_loss_plus_all_reservations_and_proposed_risk_at_most_50',
    'daily_halt': 'latched_until_next_dublin_day_cancel_unfilled_reservations',
    'unresolved': 'retain_capital_and_risk_indefinitely_block_all_new_entries',
    'entry_recheck': 'all_current_risk_and_timing_checks_before_every_fill',
    'source_order': 'global_durable_sequence_clamped_to_receipt_time',
    'scope': 'approved_notified_long_USD_stocks_reference_quote_simulation_only'}
EXPERIMENT = '2080e2e70d7380759e1269d0b5603d6533d4e7ddc079cd354451182dc135a13f'
SOURCES = ['https://helpcentre.trading212.com/hc/en-us/articles/360007081637-What-are-the-applicable-stock-exchange-fees',
    'https://helpcentre.trading212.com/hc/en-us/articles/11669719976093-What-is-a-multi-currency-account',
    'https://docs.alpaca.markets/us/docs/paper-trading']


def validate_bindings():
    if digest(GUARDED_PROTOCOL) != PROTOCOL['source_protocol_id'] or digest(CLOCK_PROTOCOL) != CLOCK_ID:
        raise ValueError('manual_portfolio_source_binding')
    if PROFILES != COST_MODEL['profiles'] or any(COST_PROTOCOL[k] != COST_MODEL[k] for k in
            ('sec_sale_rate', 'finra_usd_per_share', 'fee_schedule_checked', 'fee_schedule_expires')):
        raise ValueError('manual_portfolio_cost_binding')
    if digest(PROTOCOL) != EXPERIMENT:
        raise ValueError('manual_portfolio_protocol_binding')


def serial(value):
    return json.loads(json.dumps(value, default=lambda v: money(v) if isinstance(v, D) else str(v)))


class ManualBook(Book):
    def __init__(self, cost_profile, delay_seconds, profile):
        super().__init__(cost_profile, 'notified_manual')
        self.settings = validate_profile(profile)
        if delay_seconds not in self.settings['tested_response_delays_seconds']:
            raise ValueError('undeclared_manual_delay')
        self.delay = delay_seconds
        self.days = {}
        self.ledger = []
        self.last_at = None
        self.realized_peak = self.balance
        self.realized_drawdown = D(0)

    def day(self, now):
        key = aware(now).astimezone(ZONE).date().isoformat()
        if key not in self.days:
            self.days[key] = {'day': key, 'starting_balance_eur': self.balance,
                'realized_pnl_eur': D(0), 'closed': 0, 'halt_latched': False, 'halted_at': None}
        return self.days[key]

    def note(self, row, now, *, kind=None):
        capital, risk = self.committed()
        self.ledger.append({'at': aware(now).isoformat(), 'kind': kind or row['state'],
            'setup_id': row['setup_id'] if row else None,
            'reason': row['reason'] if row else 'daily_loss_halt',
            'net_pnl_eur': money(row['pnl']) if row and row['pnl'] is not None else None,
            'balance_eur': money(self.balance), 'reserved_capital_eur': money(capital),
            'reserved_risk_eur': money(risk), 'day': self.day(now)['day'],
            'daily_halt_latched': self.day(now)['halt_latched']})

    def cancel_pending(self, now, reason):
        for row in self.rows.values():
            if row['state'] == 'reserved':
                row.update(state='cancelled', reason=reason)
                self.note(row, now)

    def advance(self, now):
        now = aware(now)
        if self.last_at is not None and now < self.last_at:
            raise ValueError('manual_book_clock_reversed')
        self.last_at = now
        self.day(now)
        for row in self.rows.values():
            plan = row['plan']
            if row['state'] == 'reserved' and now >= min(aware(plan['expires_at']),
                    aware(plan['exit_by']) - timedelta(seconds=30)):
                row.update(state='expired', reason='no_observed_eligible_entry')
                self.note(row, now)
            elif row['state'] == 'open':
                if now >= aware(plan['exit_by']):
                    row.update(state='unresolved', reason='no_observed_exit_before_cutoff')
                    self.note(row, now)
                elif (now - aware(row['last_quote_at'])).total_seconds() > 60:
                    row.update(state='unresolved', reason='open_quote_gap_exceeded_60_seconds')
                    self.note(row, now)
        if any(row['state'] == 'unresolved' for row in self.rows.values()):
            self.cancel_pending(now, 'unresolved_exposure')

    def current_gate(self, row, now):
        others = [r for r in self.rows.values() if r is not row and r['state'] in ACTIVE]
        capital = sum((r['capital'] for r in others), D(0))
        risk = sum((r['risk'] for r in others), D(0))
        daily = self.day(now)
        return risk_gate(self.settings, as_of=now, state_day=daily['day'],
            available_capital_eur=max(D(0), self.balance-capital), reserved_risk_eur=risk,
            today_net_realized_pnl_eur=daily['realized_pnl_eur'], proposed_capital_eur=row['capital'],
            proposed_risk_eur=row['risk'], active_positions=len(others),
            daily_halt_latched=daily['halt_latched'],
            risk_estimate_complete=not any(r['state']=='unresolved' for r in others))

    def admit_alert(self, clock, body, plan, now, *, known_stop_cross=False):
        key = clock['setup_id']
        if key in self.rows:
            raise ValueError('duplicate_manual_admission')
        self.advance(now)
        prior_peak = (self.peak_capital, self.peak_risk)
        super().admit(key, body, plan, now)
        row = self.rows[key]
        ready = max(aware(now), aware(clock['acknowledged_at'])+timedelta(seconds=self.delay))
        row.update(acknowledged_at=clock['acknowledged_at'], ready_at=ready.isoformat(),
            entry_observed_at=None, last_quote_at=None)
        if row['state'] == 'reserved':
            deadline = min(aware(plan['expires_at']), aware(plan['exit_by'])-timedelta(seconds=30))
            local = ready.astimezone(ZONE)
            if known_stop_cross:
                row.update(state='invalidated', reason='stop_crossed_before_entry')
            elif ready >= deadline:
                row.update(state='blocked', reason='response_exceeds_entry_window')
            elif (local.weekday() >= 5 or local.strftime('%H:%M') >= '22:00'
                    or local.date() != aware(clock['acknowledged_at']).astimezone(ZONE).date()
                    or local.date() != aware(plan['exit_by']).astimezone(ZONE).date()):
                row.update(state='blocked', reason='manual_session_or_intraday_cutoff')
            else:
                gate = self.current_gate(row, now)
                if gate['status'] != 'profile_checks_passed':
                    reason = 'unresolved_exposure' if gate['status']=='unknown' else gate['reasons'][0]
                    row.update(state='blocked', reason=reason)
        if row['state'] != 'reserved':
            self.peak_capital, self.peak_risk = prior_peak
        self.note(row, now)

    def quote(self, candidate, quote, now):
        now = aware(now)
        self.advance(now)
        observed = aware(quote['observed_at'])
        bid, ask = dec(quote['bid']), dec(quote['ask'])
        if not 0 < bid <= ask:
            raise ValueError('manual_invalid_quote')
        if not 0 <= (now-observed).total_seconds() <= 60:
            return
        spread = (ask-bid)/((ask+bid)/2)*10000
        slip = D(PROFILES[self.profile]['slippage_bps'])/10000
        for row in self.rows.values():
            if row['candidate_id'] != candidate or row['state'] not in {'reserved', 'open'}:
                continue
            if observed < aware(row['at']):
                continue
            plan = row['plan']
            if row['state'] == 'open' and observed <= aware(row['entry_observed_at']):
                continue
            exit_reason = ('scheduled_exit' if now >= aware(plan['exit_by'])-timedelta(seconds=30)
                else 'stop' if bid <= dec(plan['stop_eur'])
                else 'target' if bid >= dec(plan['target_eur']) else None)
            if spread > 20:
                if row['state'] == 'open' and exit_reason:
                    row.update(state='unresolved', reason='exit_quote_quality_unresolved')
                    self.note(row, now)
                    self.cancel_pending(now, 'unresolved_exposure')
                continue
            if row['state'] == 'reserved':
                if bid <= dec(plan['stop_eur']):
                    row.update(state='invalidated', reason='stop_crossed_before_entry')
                    self.note(row, now)
                    continue
                gate = timing_gate(self.settings, delay_seconds=self.delay, as_of=now,
                    alert_received_at=row['acknowledged_at'], decision_available_at=row['at'],
                    quote_observed_at=observed, quote_received_at=now,
                    expires_at=plan['expires_at'], exit_by=plan['exit_by'], session_permitted=True)
                if gate['status'] != 'profile_checks_passed':
                    continue
                risk = self.current_gate(row, now)
                if risk['status'] != 'profile_checks_passed':
                    row.update(state='cancelled', reason='unresolved_exposure' if risk['status']=='unknown' else risk['reasons'][0])
                    self.note(row, now)
                    continue
                if not dec(plan['entry_eur']) <= ask <= dec(plan['entry_eur'])*D('1.002'):
                    continue
                fill = ask*(1+slip)
                e = estimate(self.profile, plan, entry=fill, quantity=row['quantity'])
                if e['rr'] < 2 or e['risk'] > row['risk'] or e['capital'] > row['capital']:
                    continue
                row.update(state='open', reason='observed_reference_entry', entry_at=now.isoformat(),
                    entry_observed_at=observed.isoformat(), last_quote_at=now.isoformat(),
                    entry_price=fill, entry_reference=ask, spread_bps=spread)
                self.note(row, now)
                continue
            row['last_quote_at'] = now.isoformat()
            if exit_reason:
                fill = bid*(1-slip)
                parts = fees(self.profile, entry=row['entry_price'], exit_price=fill,
                    quantity=row['quantity'], fx=dec(plan['fx_rate']))
                total = sum(parts.values())
                pnl = (fill-row['entry_price'])*row['quantity']-total
                row.update(state='closed', reason=exit_reason, exit_at=now.isoformat(),
                    exit_price=fill, pnl=pnl, fee_total=total, fees=parts,
                    slippage_cost=((row['entry_price']-row['entry_reference'])+(bid-fill))*row['quantity'])
                self.balance += pnl
                daily = self.day(now)
                daily['realized_pnl_eur'] += pnl
                daily['closed'] += 1
                self.realized_peak = max(self.realized_peak, self.balance)
                self.realized_drawdown = max(self.realized_drawdown, self.realized_peak-self.balance)
                self.note(row, now)
                if daily['realized_pnl_eur'] <= -D(50) and not daily['halt_latched']:
                    daily.update(halt_latched=True, halted_at=now.isoformat())
                    self.note(None, now, kind='daily_halt')
                    self.cancel_pending(now, 'daily_loss_halt')

    def snapshot(self):
        return serial({'scenario': self.profile+':'+str(self.delay), 'balance': self.balance,
            'days': self.days, 'rows': self.rows, 'ledger': self.ledger,
            'peak_capital': self.peak_capital, 'peak_risk': self.peak_risk,
            'realized_drawdown': self.realized_drawdown})

    def report(self, now):
        result = super().report()
        # All rows remain in the full ledger; bound nine-account transport.
        result['details'] = result['details'][-8:]
        result['details_omitted'] = result['considered']-len(result['details'])
        result.update(scenario=self.profile+':'+str(self.delay), delay_seconds=self.delay,
            active_positions=sum(r['state'] in ACTIVE for r in self.rows.values()),
            unresolved_exposure=any(r['state']=='unresolved' for r in self.rows.values()),
            daily_state=serial(self.day(now)), daily_history=serial(list(self.days.values())[-10:]),
            daily_history_omitted=max(0,len(self.days)-10),
            halted_days=sum(d['halt_latched'] for d in self.days.values()),
            realized_drawdown_eur=money(self.realized_drawdown) if result['closed'] else None,
            ledger_events=len(self.ledger), state_sha256=digest(self.snapshot()))
        for detail in result['details']:
            row = self.rows[detail['setup_id']]
            detail.update(acknowledged_at=row['acknowledged_at'], ready_at=row['ready_at'])
            if row['state'] not in ACTIVE:
                detail['reserved_capital_eur'] = detail['reserved_risk_eur'] = '0'
        return result


def bind(clock, review):
    packet, decision = review['packet'], review['decision']
    body = packet['packet']
    if (digest(body) != packet['packet_id'] or packet['packet_id'] != clock['packet_id']
            or decision['verdict'] != 'PAPER_WATCH_FOR_ENTRY'
            or decision['candidate_id'] != clock['candidate_id']
            or body['candidate_id'] != clock['candidate_id']
            or digest(decision['plan']) != clock['plan_sha256']
            or aware(decision['evaluated_at']) != aware(clock['decision_at'])
            or paper_attempt_id(packet, now=aware(body['assembled_at'])) != clock['setup_id']):
        raise ValueError('manual_portfolio_review_binding')
    return body, decision['plan']


def replay(events, *, now, profile, dataset_kind='forward', ledger_output=None):
    """Production inputs first pass LiveComparison and clock validators in collect.

    now is a fixed evaluation watermark taken BEFORE remote reads, preventing
    late-arriving source events from repairing past decisions with hindsight.
    """
    validate_bindings()
    validate_profile(profile)
    now = aware(now)
    if dataset_kind not in ('forward', 'synthetic'):
        raise ValueError('manual_portfolio_dataset')
    books = [ManualBook(cost, delay, profile) for cost in PROFILES for delay in (60,180,300)]
    reviews, clocks, admitted, seen = {}, {}, set(), {}
    awaiting_by_symbol, stop_crosses = {}, {}
    sequence = -1
    at = aware(PROTOCOL['since']+'T00:00:00+00:00')
    ordered = events.ordered() if isinstance(events, EventArchive) else sorted(events,key=lambda e:e['seq'])
    used = source_count = clock_count = 0
    for event in ordered:
        experiment = event['experiment_id']
        if (experiment not in (PROTOCOL['source_protocol_id'], CLOCK_ID)
                or event_id(experiment,event) != event['event_id']
                or type(event['seq']) is not int or event['seq'] <= 0
                or event['day'] != aware(event['occurred_at']).date().isoformat()
                or event['day'] < PROTOCOL['since']):
            raise ValueError('manual_portfolio_event_identity')
        if event['event_id'] in seen:
            if seen[event['event_id']] != digest(event):
                raise ValueError('manual_portfolio_conflicting_duplicate')
            continue
        if event['seq'] <= sequence:
            raise ValueError('manual_portfolio_sequence')
        sequence = event['seq']; seen[event['event_id']] = digest(event)
        at = max(at, aware(event['occurred_at']), aware(event['received_at']))
        if at > now:
            break
        used += 1
        for book in books:
            book.advance(at)
        p = json.loads(event['payload_json'])
        if p.get('dataset_kind') != 'forward' or p.get('trade_authorized') is not False:
            raise ValueError('manual_portfolio_source_scope')
        key = None
        if experiment == CLOCK_ID:
            if event['kind'] != 'audit':
                raise ValueError('manual_portfolio_clock_kind')
            clock = validate_clock(p)
            if aware(clock['recorded_at']) != aware(event['occurred_at']):
                raise ValueError('manual_portfolio_clock_time')
            key = clock['packet_id']
            if key in clocks:
                raise ValueError('duplicate_manual_portfolio_clock')
            clocks[key] = (clock, at); clock_count += 1
        else:
            source_count += 1
            if event['kind'] == 'review':
                key = p['packet']['packet_id']
                if key in reviews:
                    raise ValueError('duplicate_manual_portfolio_review')
                reviews[key] = (p,at)
                awaiting_by_symbol.setdefault(p['packet']['packet']['candidate_id'],set()).add(key)
            elif event['kind'] == 'quote':
                quote=p['quote'];observed=aware(quote['observed_at'])
                bid,ask=dec(quote['bid']),dec(quote['ask'])
                if 0<bid<=ask and 0<=(at-observed).total_seconds()<=60 and (ask-bid)/((ask+bid)/2)*10000<=20:
                    for pending in awaiting_by_symbol.get(p['candidate_id'],()):
                        decision=reviews[pending][0]['decision']
                        if (decision['verdict']=='PAPER_WATCH_FOR_ENTRY'
                                and observed>=aware(decision['evaluated_at'])
                                and bid<=dec(decision['plan']['stop_eur'])):
                            stop_crosses[pending]=max(stop_crosses.get(pending,observed),observed)
                for book in books:
                    book.quote(p['candidate_id'],p['quote'],at)
        if key is not None and key in clocks and key in reviews and key not in admitted:
            c, ca = clocks[key]; r, ra = reviews[key]
            body, plan = bind(c,r)
            crossed=key in stop_crosses and stop_crosses[key]>=aware(c['acknowledged_at'])
            for book in books:
                book.admit_alert(c,body,plan,max(ca,ra),known_stop_cross=crossed)
            admitted.add(key)
            awaiting_by_symbol[body['candidate_id']].discard(key)
            if len(admitted) > 20000:
                raise ValueError('manual_portfolio_cohort_capacity')
    for book in books:
        book.advance(now)
    ledgers = [b.snapshot() for b in books]
    if ledger_output is not None:
        ledger_output.extend(ledgers)
    result = {'schema_version':'manual-portfolio-report-v1', 'protocol_id':EXPERIMENT,
        'profile_id':PROTOCOL['profile_id'], 'clock_protocol_id':CLOCK_ID,
        'source_protocol_id':PROTOCOL['source_protocol_id'], 'since':PROTOCOL['since'],
        'as_of':now.isoformat(), 'evaluated_through':now.isoformat(),
        'evaluation_day':now.date().isoformat(), 'risk_timezone':'Europe/Dublin',
        'dataset_kind':dataset_kind, 'trade_authorized':False, 'strategy_input':False,
        'model_calls':0, 'portfolio_evaluated':True, 'broker_executable':False,
        'costs_verified':False, 'device_receipt_observed':False,
        'clock_basis':PROTOCOL['clock_basis'], 'primary_scenario':PROTOCOL['primary_scenario'],
        'state':'before_validation_start' if now.date().isoformat()<PROTOCOL['since'] else
                'evaluated' if clock_count else 'no_confirmed_alert_clocks',
        'source_events':len(events), 'processed_events':used,
        'source_sha256':events.source_digest() if isinstance(events,EventArchive) else digest(events),
        'clocks':clock_count, 'matched_clocks':len(admitted),
        'unmatched_clocks':clock_count-len(admitted), 'comparison_events_processed':source_count,
        'initial_balance_eur':'1000', 'daily_loss_limit_eur':'50', 'per_trade_risk_eur':'20',
        'combined_risk_limit_eur':'40', 'allocation_limit_eur':'500', 'position_limit':3,
        'cost_model':deepcopy(COST_MODEL), 'cost_sources':SOURCES,
        'ledger_sha256':digest(ledgers), 'books':[b.report(now) for b in books],
        'note':'Nine alternative fictional accounts; never add balances or results. Telegram acknowledgement is not a user read receipt. '
            'Daily loss uses realized net trading P/L plus reserved risk; a EUR50 realized loss latches a halt until the next Dublin date. '
            'Gap losses can exceed planned limits. Missing exits or open quote gaps over 60 seconds retain exposure and block new entries. '
            'Costs, slippage, frozen FX conversion and quote liquidity are assumptions; AI costs are excluded. No marked-to-market equity. '
            'Only notified approved USD-stock setups are represented; upstream rejections and missing acknowledgement clocks are absent. '
            'Session permission uses the original approved plan window, not a new halt/exchange check. No real orders.'}
    if len(canonical(result).encode()) > 175000:
        raise ValueError('manual_portfolio_report_capacity')
    return result


def collect(client, *, now, root, diagnostics):
    """No alerts means no large quote read. Past days with alerts are never reset."""
    validate_bindings()
    now = aware(now)
    first = aware(PROTOCOL['since']+'T00:00:00+00:00').date()
    days = (now.date()-first).days+1
    if days > 366:
        raise ValueError('manual_portfolio_history_capacity')
    archive = EventArchive()
    try:
        for n in range(max(0,days)):
            day = (first+timedelta(days=n)).isoformat()
            clocks = read_clocks(client,day)
            clocks = [e for e in clocks if max(aware(e['occurred_at']),aware(e['received_at'])) <= now]
            diagnostics.append({'day':day,'clocks':len(clocks),'source_loaded':bool(clocks)})
            if not clocks:
                continue
            worker = LiveComparison(Path(root)/day, client=client, day=day,
                clock=lambda:now, protocol=GUARDED_PROTOCOL)
            worker.sync()
            source = worker.root/'comparison-events.jsonl'
            if source.exists():
                with source.open() as lines:
                    for line in lines:
                        archive.append(json.loads(line))
            for clock in clocks:
                archive.append(clock)
        return archive
    except BaseException:
        archive.close()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/manual-portfolio'))
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    cutoff=datetime.now(UTC)
    profile=validate_profile(json.loads(PROFILE_PATH.read_text()))
    client=EventClient(os.environ.get('REVIEW_INGEST_SECRET'))
    diagnostics=[]
    with TemporaryDirectory() as scratch:
        source=collect(client,now=cutoff,root=scratch,diagnostics=diagnostics)
    with source:
        ledgers=[]
        report=replay(source,now=cutoff,profile=profile,ledger_output=ledgers)
        args.output.mkdir(parents=True,exist_ok=True)
        with gzip.open(args.output/'source-events.jsonl.gz','wt') as out:
            for event in source:
                out.write(canonical(event)+'\n')
        with gzip.open(args.output/'ledger.json.gz','wt') as out:
            out.write(canonical(ledgers))
        with EventArchive() as restored:
            with gzip.open(args.output/'source-events.jsonl.gz','rt') as lines:
                for line in lines:
                    restored.append(json.loads(line))
            recovered=[]
            if replay(restored,now=cutoff,profile=profile,ledger_output=recovered) != report or recovered != ledgers:
                raise ValueError('manual_portfolio_restore_mismatch')
        with gzip.open(args.output/'ledger.json.gz','rt') as saved:
            if json.load(saved) != ledgers:
                raise ValueError('manual_portfolio_ledger_restore_mismatch')
        generated=datetime.now(UTC)
        report.update(as_of=generated.isoformat(),evaluation_day=generated.date().isoformat())
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        (args.output/'source-health.json').write_text(json.dumps({'days':diagnostics,
            'source_bytes':source.size_bytes,'restore_verified':True,'model_calls':0},indent=2)+'\n')
        if args.publish:
            client.append(EXPERIMENT,[envelope('audit',report,generated)])
        print(json.dumps({'state':report['state'],'published':args.publish,'clocks':report['clocks'],
            'scenarios':len(report['books']),'restore_verified':True,'model_calls':0,'orders':0}))


if __name__ == '__main__':
    main()
