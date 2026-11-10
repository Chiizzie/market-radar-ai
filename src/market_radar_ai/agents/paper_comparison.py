"""Prospective code/AI comparison journal. No providers, models, alerts or orders."""
import json
import sqlite3
from contextlib import contextmanager
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from .candidate_packages import canonical, digest
from .paper_outcomes import Quote, replay_long
from .paper_review_prompts import VERSION as REVIEW_POLICY_VERSION
from .paper_team import PaperPlan
from .paper_verdict import STAGES, VerdictReview, paper_attempt_id, paper_gate
from .setup_checks import validate_paper_plan
from .review_policy import team_approval_allowed

PROTOCOL = {
    'version': 'paper-comparison-v1',
    'code_strategy_version': 'opening30m-continuation20-pullback-v3',
    'review_policy_version': REVIEW_POLICY_VERSION,
    'baseline_entry_clock': 'enrolment_before_review',
    'ai_entry_clock': 'fresh_final_approval',
    'fill_clock': 'local_receipt_not_backdated_exchange_time',
    'entry_mode': 'breakout',
    'exit_window_seconds': 30,
    'maximum_entry_spread_bps': '20',
    'maximum_entry_gap_bps': '20',
    'currency': 'EUR',
    'maximum_planned_loss_eur': '20',
    'prices': 'reference_venue_only',
    'costs': 'fixed_plan_assumptions_plus_separate_recorded_AI_cost',
}


def aware(value):
    at = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('aware_comparison_clock_required')
    return at.astimezone(UTC)


def validate_packet(packet, now):
    body = packet['packet']
    if (digest(body) != packet['packet_id'] or body['schema_version'] != 'paper-review-packet-v1'
            or body['live_trade_authorized'] is not False
            or body['candidate_id'] not in ('stocks:' + body['symbol'], 'crypto:' + body['symbol'])
            or not body['source_ids'] or set(body['source_ids']) != set(body['sources'])
            or len(body['source_ids']) != len(set(body['source_ids']))
            or not aware(body['assembled_at']) <= aware(now) < aware(body['review_deadline'])):
        raise ValueError('invalid_comparison_packet')
    row = {'market': 'stocks' if body['candidate_id'].startswith('stocks:') else 'crypto',
           'symbol': body['symbol'], 'conditional_paper_plan': body['plan'],
           'reference_checks': body['reference_checks'], 'technical_checks': body['technical_checks'],
           'current_news_source_ids': [s for s in body['source_ids'] if s.startswith('news:')]}
    news_checks = [v for k,v in body['sources'].items() if k.startswith('news_check:')]
    row['chart_news_check'] = news_checks[0] if len(news_checks) == 1 else None
    if not paper_gate(row, now=aware(now))['eligible_for_paper_review']:
        raise ValueError('comparison_requires_code_qualified_packet')
    return body


def cohort_snapshot(packets, *, now):
    """Persist before selection/model access; this is not observation coverage."""
    for packet in packets:
        validate_packet(packet, now)
    body = {'schema_version': 'paper-comparison-cohort-v1', 'recorded_at': aware(now).isoformat(),
            'protocol': PROTOCOL, 'packets': packets, 'trade_authorized': False,
            'observations_started': False}
    return json.loads(canonical({**body, 'cohort_sha256': digest(body)}))


def _plan(value):
    return PaperPlan(entry=value['entry_eur'], stop=value['stop_eur'],
                     target=value['target_eur'], quantity=value['quantity'],
                     costs_eur=value['assumed_round_trip_cost_eur'],
                     invalidation=value['invalidation'], exit_by=value['exit_by'])


def _outcome(plan, observations, *, start, now):
    # Receipt is the earliest time the observer could act. Preserve the exchange
    # time separately; a late-received quote cannot backdate an entry or exit.
    quotes = [Quote(observed_at=x['received_at'], bid=x['quote']['bid'], ask=x['quote']['ask'])
              for x in observations if start <= aware(x['quote']['observed_at'])
              and start <= aware(x['received_at']) <= now]
    result = replay_long(_plan(plan), quotes, decision_at=start,
                         entry_expires_at=aware(plan['expires_at']),
                         entry_mode='breakout', exit_window_seconds=30,
                         maximum_entry_spread_bps=Decimal('20'),maximum_entry_gap_bps=Decimal('20'))
    state = result.status
    if state == 'not_filled' and result.reason == 'no_observed_eligible_fill' and now < aware(plan['expires_at']):
        state = 'watching'
    elif state == 'unresolved' and now < aware(plan['exit_by']):
        state = 'open_simulation'
    return {'state': state, 'outcome': result.model_dump(mode='json'),
            'observations_available': len(quotes)}


def metrics(arms):
    closed = [a['outcome'] for a in arms if a['state'] == 'closed']
    values = [Decimal(o['net_pnl_eur']) for o in closed]
    gains = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    exits = defaultdict(Decimal)
    for outcome in closed:
        exits[aware(outcome['exit_at'])] += Decimal(outcome['net_pnl_eur'])
    equity = peak = drawdown = Decimal(0)
    for at in sorted(exits):
        equity += exits[at]
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {'states': dict(sorted(Counter(a['state'] for a in arms).items())),
            'closed': len(closed), 'wins': len(gains), 'losses': len(losses),
            'breakeven': len(values) - len(gains) - len(losses),
            'closed_net_pnl_eur': str(sum(values)) if values else None,
            'average_closed_pnl_eur': str(sum(values) / len(values)) if values else None,
            'average_gain_eur': str(sum(gains) / len(gains)) if gains else None,
            'average_loss_eur': str(sum(losses) / len(losses)) if losses else None,
            'realized_closed_drawdown_eur': str(drawdown) if values else None}


class ComparisonStore:
    """Separate SQLite experiment, never an approved-trade journal.

    Protocol and dataset kind are immutable. Reopening a database cannot reset its
    cohort, observations or review decisions. Different strategies require a new
    experiment, so later rule changes cannot rewrite an earlier comparison.
    """
    def __init__(self, path, *, dataset_kind='forward', protocol=None):
        if dataset_kind not in ('forward', 'synthetic'):
            raise ValueError('invalid_comparison_dataset_kind')
        self._batch_db = None
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.protocol = json.loads(canonical(protocol or PROTOCOL))
        if self.protocol != PROTOCOL:
            raise ValueError('unsupported_comparison_protocol')
        self.dataset_kind = dataset_kind
        meta = canonical({'protocol': self.protocol, 'dataset_kind': dataset_kind})
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS comparison_meta (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS comparison_cohort (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            # Derived from immutable payloads, not an independently writable cache.
            # SQLite maintains/rebuilds it across transactions, rollback and reopen.
            db.execute("CREATE INDEX IF NOT EXISTS comparison_candidate_enrolment ON comparison_cohort "
                       "(json_extract(payload,'$.packet.packet.candidate_id'),json_extract(payload,'$.enrolled_at'))")
            db.execute('CREATE TABLE IF NOT EXISTS comparison_reviews (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS comparison_attempts (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS comparison_costs (id TEXT, at TEXT, payload TEXT NOT NULL, PRIMARY KEY(id,at))')
            db.execute('CREATE TABLE IF NOT EXISTS comparison_quotes (candidate TEXT, at TEXT, payload TEXT NOT NULL, PRIMARY KEY(candidate,at))')
            prior = db.execute('SELECT payload FROM comparison_meta WHERE id=1').fetchone()
            if prior and prior[0] != meta:
                raise ValueError('comparison_protocol_or_dataset_changed')
            db.execute('INSERT OR IGNORE INTO comparison_meta VALUES (1,?)', (meta,))

    @contextmanager
    def connection(self):
        if self._batch_db is not None:
            yield self._batch_db
            return
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def replay_batch(self):
        """One atomic transaction per authenticated page, retaining all checks."""
        if self._batch_db is not None:
            raise ValueError('nested_comparison_replay')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self._batch_db = db
            try:
                yield
            finally:
                self._batch_db = None

    def enrol(self, packet, *, now):
        now = aware(now)
        body = validate_packet(packet, now)
        key = paper_attempt_id(packet, now=aware(body['assembled_at']))
        value = {'packet': packet, 'enrolled_at': now.isoformat()}
        with self.connection() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT payload FROM comparison_cohort WHERE id=?', (key,)).fetchone()
            if prior:
                if aware(json.loads(prior[0])['enrolled_at']) > now:
                    raise ValueError('cannot_backdate_comparison_enrolment')
                return key
            db.execute('INSERT INTO comparison_cohort VALUES (?,?)', (key, canonical(value)))
        return key

    def _cohort(self, db, key):
        row = db.execute('SELECT payload FROM comparison_cohort WHERE id=?', (key,)).fetchone()
        if row is None:
            raise ValueError('comparison_candidate_not_enrolled')
        return json.loads(row[0])

    def begin_review(self, packet, *, now):
        """Call before model access, never retrospectively after reading outcomes."""
        now = aware(now)
        body = validate_packet(packet, now)
        key = paper_attempt_id(packet, now=aware(body['assembled_at']))
        with self.connection() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            cohort = self._cohort(db, key)
            if aware(cohort['enrolled_at']) > now:
                raise ValueError('review_precedes_comparison_enrolment')
            if db.execute('SELECT 1 FROM comparison_attempts WHERE id=?', (key,)).fetchone():
                raise ValueError('comparison_review_already_started')
            db.execute('INSERT INTO comparison_attempts VALUES (?,?)',
                       (key, canonical({'packet_id': packet['packet_id'], 'started_at': now.isoformat()})))
        return key

    def observe(self, candidate_id, quote, *, source, received_at):
        received_at = aware(received_at)
        quote = Quote.model_validate(quote.model_dump())
        if (not isinstance(source, str) or not 1 <= len(source) <= 200
                or quote.bid > quote.ask or not 0 <= (received_at - quote.observed_at).total_seconds() <= 60):
            raise ValueError('fresh_uncrossed_comparison_quote_required')
        quote = quote.model_copy(update={'observed_at': aware(quote.observed_at)})
        value = {'quote': quote.model_dump(mode='json'), 'received_at': received_at.isoformat(),
                 'source': source, 'currency': 'EUR'}
        payload = canonical(value)
        with self.connection() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            # Read only the indexed candidate's enrolment timestamps. Decoding
            # every full evidence packet here made replay scale as quotes × cohorts.
            enrolled = db.execute("SELECT json_extract(payload,'$.enrolled_at') FROM comparison_cohort "
                                  "WHERE json_extract(payload,'$.packet.packet.candidate_id')=?", (candidate_id,))
            # Compare aware datetimes in Python: ISO strings can differ in fractional
            # precision, so SQL string ordering is not a safe time gate.
            if not any(aware(row[0]) <= quote.observed_at for row in enrolled):
                raise ValueError('observe_only_after_comparison_enrolment')
            old = db.execute('SELECT payload FROM comparison_quotes WHERE candidate=? AND at=?',
                             (candidate_id, received_at.isoformat())).fetchone()
            if old and old[0] != payload:
                raise ValueError('comparison_observation_is_immutable')
            db.execute('INSERT OR IGNORE INTO comparison_quotes VALUES (?,?,?)',
                       (candidate_id, received_at.isoformat(), payload))

    def record_review(self, packet, audit, decision, *, now):
        now = aware(now)
        body = packet['packet']
        key = paper_attempt_id(packet, now=aware(body['assembled_at']))
        reports = [VerdictReview.model_validate(r) for r in audit['reviews']]
        if (digest(body) != packet['packet_id'] or audit['packet_id'] != packet['packet_id']
                or audit['schema_version'] != 'paper-ai-review-v1' or audit['trade_authorized'] is not False
                or [r.stage for r in reports] != STAGES
                or any(r.packet_id != packet['packet_id'] or not set(r.source_ids) <= set(body['source_ids'])
                       or len(set(r.source_ids)) != len(r.source_ids)
                       or list(r.reviewed_stages) != (STAGES[:i] if i >= 6 else [])
                       for i, r in enumerate(reports))
                or decision['packet_id'] != packet['packet_id'] or decision['candidate_id'] != body['candidate_id']
                or decision['schema_version'] != 'paper-final-decision-v1'
                or decision.get('review_policy_version') != body.get('review_policy_version')
                or decision['paper_only'] is not True or decision['trade_authorized'] is not False
                or decision['live_orders_enabled'] is not False
                or not aware(body['assembled_at']) <= aware(audit['completed_at']) <= aware(decision['evaluated_at']) <= now):
            raise ValueError('invalid_comparison_review_chain')
        if decision['verdict'] == 'PAPER_WATCH_FOR_ENTRY':
            if (decision['blockers'] or not team_approval_allowed((r.verdict for r in reports),
                    policy_version=body.get('review_policy_version'))
                    or validate_paper_plan(decision['plan'], now=aware(decision['evaluated_at']))['state'] != 'PASS'
                    or aware(decision['evaluated_at']) >= aware(body['review_deadline'])
                    or {k: v for k, v in decision['plan'].items() if k != 'expires_at'}
                       != {k: v for k, v in body['plan'].items() if k != 'expires_at'}):
                raise ValueError('invalid_comparison_approval')
        elif decision['verdict'] != 'NO_ACTION' or decision['plan'] is not None or not decision['blockers']:
            raise ValueError('invalid_comparison_rejection')
        value = canonical({'packet': packet, 'audit': audit, 'decision': decision,
                           'received_at': now.isoformat()})
        with self.connection() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            cohort = self._cohort(db, key)
            attempted = db.execute('SELECT payload FROM comparison_attempts WHERE id=?', (key,)).fetchone()
            if attempted is None:
                raise ValueError('prospective_review_start_required')
            attempt = json.loads(attempted[0])
            if (attempt['packet_id'] != packet['packet_id']
                    or not aware(cohort['enrolled_at']) <= aware(attempt['started_at']) <= aware(audit['completed_at'])):
                raise ValueError('review_precedes_comparison_enrolment')
            old = db.execute('SELECT payload FROM comparison_reviews WHERE id=?', (key,)).fetchone()
            if old:
                prior = json.loads(old[0])
                if any(prior[k] != json.loads(value)[k] for k in ('packet', 'audit', 'decision')):
                    raise ValueError('comparison_review_is_immutable')
                return key
            db.execute('INSERT INTO comparison_reviews VALUES (?,?)', (key, value))
        return key

    def record_cost(self, key, *, settled_microeur, held_microeur, complete, now):
        if (type(settled_microeur) is not int or settled_microeur < 0
                or type(held_microeur) is not int or held_microeur < 0
                or type(complete) is not bool or (complete and held_microeur)):
            raise ValueError('invalid_comparison_cost_record')
        value = {'settled_microeur': settled_microeur, 'held_microeur': held_microeur,
                 'complete': complete, 'recorded_at': aware(now).isoformat()}
        with self.connection() as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            self._cohort(db, key)
            row = db.execute('SELECT payload FROM comparison_costs WHERE id=? ORDER BY at DESC LIMIT 1', (key,)).fetchone()
            if row:
                old = json.loads(row[0])
                if all(old[k] == value[k] for k in ('settled_microeur', 'held_microeur', 'complete')):
                    return
                if old['complete'] or old['settled_microeur'] > settled_microeur or aware(old['recorded_at']) >= aware(now):
                    raise ValueError('cannot_rewrite_settled_comparison_cost')
            db.execute('INSERT INTO comparison_costs VALUES (?,?,?)',
                       (key, aware(now).isoformat(), canonical(value)))

    def reconcile_cost(self, packet, ledger_state, *, now):
        from .github_budget import validate_state
        state = validate_state(ledger_state)
        prefix = 'paper-final-v1:' + packet['packet_id'] + ':'
        entries = [state['entries'].get(prefix + stage) for stage in STAGES]
        complete = all(e is not None and e['actual'] is not None for e in entries)
        rows = [e for e in entries if e is not None]
        key = paper_attempt_id(packet, now=aware(packet['packet']['assembled_at']))
        self.record_cost(key, settled_microeur=sum(e['actual'] for e in rows if e['actual'] is not None),
                         held_microeur=sum(e['reserved'] for e in rows if e['actual'] is None),
                         complete=complete, now=now)

    def report(self, *, now):
        now = aware(now)
        rows = []
        with self.connection() as db:
            for key, payload in db.execute('SELECT id,payload FROM comparison_cohort ORDER BY id'):
                cohort = json.loads(payload)
                if aware(cohort['enrolled_at']) > now:
                    continue
                body = cohort['packet']['packet']
                quotes = [json.loads(q[0]) for q in db.execute(
                    'SELECT payload FROM comparison_quotes WHERE candidate=? ORDER BY at', (body['candidate_id'],))]
                baseline = _outcome(body['plan'], quotes, start=aware(cohort['enrolled_at']), now=now)
                stored = db.execute('SELECT payload FROM comparison_reviews WHERE id=?', (key,)).fetchone()
                review = json.loads(stored[0]) if stored else None
                if review and aware(review['received_at']) > now:
                    review = None
                attempt = db.execute('SELECT payload FROM comparison_attempts WHERE id=?', (key,)).fetchone()
                attempted = attempt and aware(json.loads(attempt[0])['started_at']) <= now
                ai = {'state': 'review_incomplete' if attempted else 'not_reviewed', 'outcome': None}
                if review:
                    decision = review['decision']
                    ai = (_outcome(decision['plan'], quotes, start=aware(decision['evaluated_at']), now=now)
                          if decision['verdict'] == 'PAPER_WATCH_FOR_ENTRY'
                          else {'state': 'no_action', 'outcome': None})
                cost = db.execute('SELECT payload FROM comparison_costs WHERE id=? AND at<=? ORDER BY at DESC LIMIT 1',
                                  (key, now.isoformat())).fetchone()
                cost = json.loads(cost[0]) if cost else None
                rows.append({'setup_id': key, 'candidate_id': body['candidate_id'],
                             'strategy_id': body['technical_checks'].get('strategy_id', 'legacy_unspecified'),
                             'enrolled_at': cohort['enrolled_at'], 'code_only': baseline, 'ai_reviewed': ai,
                             'decision_blockers': review['decision']['blockers'] if review else None,
                             'rejected_counterfactual_only': ai['state'] == 'no_action',
                             'review_started_at': json.loads(attempt[0])['started_at'] if attempted else None,
                             'decision_at': review['decision']['evaluated_at'] if review else None,
                             'plans': {'code_only':body['plan'], 'ai_reviewed':review['decision']['plan']
                                       if review and review['decision']['verdict']=='PAPER_WATCH_FOR_ENTRY' else None},
                             'ai_cost': cost})
        paired = []
        for row in rows:
            baseline, ai = row['code_only'], row['ai_reviewed']
            if baseline['state'] != 'closed' or ai['state'] not in ('closed', 'no_action'):
                continue
            base_pnl = Decimal(baseline['outcome']['net_pnl_eur'])
            ai_pnl = Decimal(ai['outcome']['net_pnl_eur']) if ai['state'] == 'closed' else Decimal(0)
            cost = row['ai_cost']
            paired.append({'setup_id': row['setup_id'], 'delta_before_ai_cost_eur': str(ai_pnl - base_pnl),
                           'delta_after_ai_cost_eur': str(ai_pnl - base_pnl - Decimal(cost['settled_microeur']) / 1_000_000)
                           if cost and cost['complete'] else None})
        costs = [r['ai_cost'] for r in rows if r['ai_cost']]
        unknown = sum(not r['ai_cost'] or not r['ai_cost']['complete'] for r in rows)
        complete_pairs = bool(rows) and len(paired) == len(rows) and all(
            p['delta_after_ai_cost_eur'] is not None for p in paired)
        return {'schema_version': 'paper-comparison-report-v1', 'as_of': now.isoformat(),
                'dataset_kind': self.dataset_kind, 'protocol': json.loads(canonical(self.protocol)),
                'protocol_id': digest(self.protocol),
                'cohort_count': len(rows), 'rows': rows,
                'by_strategy': {strategy: {
                    'cohort_count': sum(r['strategy_id'] == strategy for r in rows),
                    'code_only': metrics([r['code_only'] for r in rows if r['strategy_id'] == strategy]),
                    'ai_reviewed': metrics([r['ai_reviewed'] for r in rows if r['strategy_id'] == strategy])}
                    for strategy in sorted({r['strategy_id'] for r in rows})},
                'code_only': metrics([r['code_only'] for r in rows]),
                'ai_reviewed': metrics([r['ai_reviewed'] for r in rows]),
                'matched_observed_pairs': paired,
                'matched_pair_count': len(paired), 'excluded_pair_count': len(rows) - len(paired),
                'complete_cohort_delta_after_ai_cost_eur': str(sum(
                    Decimal(p['delta_after_ai_cost_eur']) for p in paired)) if complete_pairs else None,
                'approved_entries_missed_or_unobserved': sum(
                    r['ai_reviewed']['state'] == 'not_filled' and r['code_only']['outcome']['entry_at'] is not None
                    for r in rows),
                'ai_costs': {'settled_estimated_eur': str(sum(c['settled_microeur'] for c in costs) / Decimal(1_000_000)),
                             'held_maximum_eur': str(sum(c['held_microeur'] for c in costs) / Decimal(1_000_000)),
                             'unreconciled_candidates': unknown,
                             'complete_total_eur': str(sum(c['settled_microeur'] for c in costs) / Decimal(1_000_000)) if not unknown else None},
                'model_calls_by_report': 0, 'trade_authorized': False,
                'note': 'Reference-quote simulations, not executable fills. Cohort is fixed before AI review. '
                        'The AI arm starts only after actual approval. Unreviewed, open, unfilled and unresolved '
                        'outcomes are not scored as wins or zero-profit trades. Rejected candidates are hypothetical '
                        'comparisons only; no-action has zero trading P/L solely in matched policy pairs. '
                        'Matched pairs exclude missing outcomes and can be selection-biased. Drawdown covers '
                        'closed realized outcomes only, not intratrade or portfolio drawdown. Unknown AI costs '
                        'are not zero. Sampling gaps can miss events. No profitability conclusion is established.'}

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists():
            raise ValueError('preserve_existing_comparison_backup')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.database.is_file():
        raise ValueError('existing_comparison_database_required')
    store = ComparisonStore(args.database, dataset_kind='synthetic' if args.synthetic else 'forward')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(store.report(now=datetime.now(UTC)), indent=2) + '\n')


if __name__ == '__main__':
    main()
