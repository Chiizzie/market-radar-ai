"""Paired manual-response paper experiment on the validated alert journal."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .candidate_packages import digest
from .manual_portfolio import EXPERIMENT as MANUAL_ID, ManualBook
from .paper_comparison import aware

ZONE = ZoneInfo('Europe/Dublin')
PROTOCOL = {
    'version': 'fresh-breakout-after-manual-response-v1',
    'manual_protocol': '2080e2e70d7380759e1269d0b5603d6533d4e7ddc079cd354451182dc135a13f',
    'validation_first_day_dublin': '2026-11-19', 'response_seconds': [180, 300],
    'universe': 'all_bound_approved_stock_telegram_watches', 'cost_profile': 'eur_conversion',
    'control': 'original_manual_plan_and_expiry',
    'alternative': 'ordinary_plan_if_still_valid_else_one_new_bid_recross',
    'recheck_window_seconds_from_response': 60, 'max_gap_seconds': 60,
    'max_cross_interval_seconds': 15, 'max_spread_bps': 20, 'max_ask_above_entry_bps': 20,
    'confirmation': 'two_distinct_post_response_quotes_bid_below_then_at_or_above_original_entry',
    'fill': 'newer_quote_after_confirmation_bid_still_above_trigger_and_ask_inside_band',
    'invalidation': 'observed_stop_or_target_touch_or_missing_continuity_since_ack',
    'risk': 'original_stop_target_quantity_ceiling_intraday_exit_and_shared_manual_risk_gates',
    'phase_accounts': 'independent_1000_EUR_per_arm_and_delay_reset_at_validation_start',
    'model_calls': 0, 'trade_authorized': False, 'automatic_promotion': False}
PROTOCOL_ID = '91a6f7767518a7d96659ec67fd2e841efc23fa61d123f3eb3c2c84a7aa0bddd4'


class Scenario:
    def __init__(self, delay, profile):
        self.delay = delay
        self.control = ManualBook(PROTOCOL['cost_profile'], delay, profile)
        self.fresh = ManualBook(PROTOCOL['cost_profile'], delay, profile)
        self.pending = {}
        self.cases = {}

    def admit(self, clock, body, plan, at, known_stop_cross):
        key = clock['setup_id']
        ack = aware(clock['acknowledged_at'])
        response = ack + timedelta(seconds=self.delay)
        ready = max(response, at)
        exit_limit = aware(plan['exit_by']) - timedelta(seconds=30)
        expiry = aware(plan['expires_at'])
        end = min(response + timedelta(seconds=PROTOCOL['recheck_window_seconds_from_response']), exit_limit)
        self.control.admit_alert(clock, body, plan, at, known_stop_cross=known_stop_cross)
        case = self.cases[key] = {'setup_id': key, 'packet_id': clock['packet_id'],
            'candidate_id': body['candidate_id'], 'acknowledged_at': clock['acknowledged_at'],
            'response_at': response.isoformat(), 'original_expiry': plan['expires_at'],
            'confirmation_at': None, 'recheck_until': end.isoformat()}
        if ready < min(expiry, exit_limit):
            self.fresh.admit_alert(clock, body, plan, at, known_stop_cross=known_stop_cross)
            case['recheck'] = 'original_window_available'
        elif known_stop_cross:
            case['recheck'] = 'original_stop_observed'
        elif ready >= end or at.astimezone(ZONE).date() != ack.astimezone(ZONE).date():
            case['recheck'] = 'no_remaining_recheck_window'
        elif (at-ack).total_seconds() > PROTOCOL['max_gap_seconds']:
            case['recheck'] = 'quote_coverage_unknown'
        else:
            case['recheck'] = 'awaiting_recross'
            self.pending[key] = {'clock': clock, 'body': body, 'plan': plan, 'ready': ready,
                'end': end, 'last': ack, 'below': None}

    def finish(self, key, state):
        self.cases[key]['recheck'] = state
        del self.pending[key]

    def advance(self, at):
        self.control.advance(at)
        self.fresh.advance(at)
        for key, p in list(self.pending.items()):
            if (min(at, p['end']) - p['last']).total_seconds() > PROTOCOL['max_gap_seconds']:
                self.finish(key, 'quote_coverage_unknown')
            elif at >= p['end']:
                self.finish(key, 'window_closed_without_confirmation')

    def quote(self, candidate, q, at):
        self.control.quote(candidate, q, at)
        self.fresh.quote(candidate, q, at)
        obs = aware(q['observed_at'])
        bid, ask = Decimal(q['bid']), Decimal(q['ask'])
        for key, p in list(self.pending.items()):
            if p['body']['candidate_id'] != candidate or obs <= p['last']:
                continue
            if not 0 <= (at-obs).total_seconds() <= PROTOCOL['max_gap_seconds']:
                continue
            plan = p['plan']
            spread = (ask-bid)/((ask+bid)/2)*10000
            stop, target, entry = (Decimal(plan[k]) for k in ('stop_eur','target_eur','entry_eur'))
            if bid <= stop or bid >= target:
                self.finish(key, 'touch_with_uncertain_quote' if spread > PROTOCOL['max_spread_bps']
                            else 'original_stop_observed' if bid <= stop else 'original_target_observed')
                continue
            if spread > PROTOCOL['max_spread_bps']:
                p['below'] = None
                continue
            p['last'] = obs
            if obs < p['ready'] or at >= p['end']:
                continue
            below = p['below']
            p['below'] = obs if bid < entry else None
            if (bid < entry or below is None or (obs-below).total_seconds() > PROTOCOL['max_cross_interval_seconds']
                    or ask > entry*(1+Decimal(PROTOCOL['max_ask_above_entry_bps'])/10000)):
                continue
            derived = {**plan, 'expires_at': p['end'].isoformat()}
            self.fresh.admit_alert(p['clock'], p['body'], derived, at)
            self.fresh.rows[key]['fresh_confirmation_observed_at'] = obs.isoformat()
            self.cases[key]['confirmation_at'] = at.isoformat()
            self.finish(key, 'fresh_bid_recross')

    def report(self):
        from .performance_intelligence import closed_metrics
        cases = []
        metrics = {}
        for arm, book in [('control', self.control), ('fresh', self.fresh)]:
            entries = [book.rows.get(key, {'state': 'not_admitted'}) for key in self.cases]
            metrics[arm] = closed_metrics(entries)
        for key, case in self.cases.items():
            result = dict(case)
            for name, book in [('control', self.control), ('fresh', self.fresh)]:
                row = book.rows.get(key)
                if row:
                    result[name] = {k: row[k] for k in ('state','reason','entry_at','exit_at')}
                    result[name]['net_pnl_eur'] = str(row['pnl']) if row['pnl'] is not None else None
                else:
                    result[name] = {'state': 'not_admitted', 'reason': case['recheck'],
                                    'entry_at': None, 'exit_at': None, 'net_pnl_eur': None}
            cases.append(result)
        return {'alerts': len(cases), 'recheck_states': dict(Counter(c['recheck'] for c in cases)),
                **metrics, 'cases': cases}


class FreshBreakout:
    def __init__(self, profile):
        if digest(PROTOCOL) != PROTOCOL_ID or MANUAL_ID != PROTOCOL['manual_protocol']:
            raise ValueError('fresh_breakout_protocol_binding')
        self.phases = {name: [Scenario(delay, profile) for delay in PROTOCOL['response_seconds']]
                       for name in ('development','validation')}
        self.active = None
        self.late_clocks = Counter()

    def advance(self, at):
        phase = 'validation' if at.astimezone(ZONE).date().isoformat() >= PROTOCOL['validation_first_day_dublin'] else 'development'
        if self.active is not None and self.active != phase:
            for s in self.phases[self.active]:
                s.advance(at)
        self.active = phase
        for s in self.phases[phase]:
            s.advance(at)

    def admit(self, clock, body, plan, at, *, known_stop_cross):
        if aware(clock['acknowledged_at']).astimezone(ZONE).date() != at.astimezone(ZONE).date():
            self.late_clocks[self.active] += 1
            return
        for s in self.phases[self.active]:
            s.admit(clock, body, plan, at, known_stop_cross)

    def quote(self, candidate, quote, at):
        for s in self.phases[self.active]:
            s.quote(candidate, quote, at)

    def report(self):
        return {'protocol_id': PROTOCOL_ID, 'protocol': PROTOCOL, 'trade_authorized': False,
            'excluded_prior_day_clocks': dict(self.late_clocks),
            'phases': {name: {str(s.delay): s.report() for s in scenarios}
                       for name, scenarios in self.phases.items()}}
