"""Append-only local paper journal for final verdicts and EUR reference quotes."""
import json
import sqlite3
from decimal import Decimal
from datetime import datetime, timezone
from .paper_team import PaperPlan
from .paper_outcomes import Quote, replay_long
from .setup_checks import validate_paper_plan


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class PaperTracker:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS tracked_plans (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS tracked_quotes (id TEXT, at TEXT, payload TEXT NOT NULL, PRIMARY KEY(id, at))')

    def register(self, decision):
        if (decision.get('schema_version') != 'paper-final-decision-v1'
            or decision.get('verdict') != 'PAPER_WATCH_FOR_ENTRY'
            or decision.get('paper_only') is not True
            or decision.get('trade_authorized') is not False
            or decision.get('live_orders_enabled') is not False
            or decision.get('blockers')):
            raise ValueError('approved_paper_decision_required')
        at = datetime.fromisoformat(decision['evaluated_at'])
        if at.tzinfo is None or validate_paper_plan(decision['plan'], now=at)['state'] != 'PASS':
            raise ValueError('invalid_plan')
        key = decision['packet_id']
        if not isinstance(key,str) or not key:
            raise ValueError('packet_id_required')
        body=canonical(decision)
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT payload FROM tracked_plans WHERE id=?',(key,)).fetchone()
            if prior and prior[0]!=body:
                raise ValueError('decision_is_immutable')
            db.execute('INSERT OR IGNORE INTO tracked_plans VALUES (?,?)',(key,body))
        return key

    def observe(self, key, quote, *, symbol, source, now):
        quote=Quote.model_validate(quote.model_dump())
        if now.tzinfo is None or not 0 <= (now-quote.observed_at).total_seconds() <= 60 or quote.bid>quote.ask or not source:
            raise ValueError('fresh_uncrossed_eur_reference_required')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM tracked_plans WHERE id=?',(key,)).fetchone()
            if not row: raise ValueError('unknown_plan')
            decision=json.loads(row[0])
            if symbol!=decision['plan']['symbol'] or quote.observed_at<datetime.fromisoformat(decision['evaluated_at']):
                raise ValueError('quote_identity_or_clock')
            quote=quote.model_copy(update={'observed_at':quote.observed_at.astimezone(timezone.utc)})
            at=quote.observed_at.isoformat()
            payload=canonical({'quote':quote.model_dump(mode='json'),'source':source,'currency':'EUR'})
            prior=db.execute('SELECT payload FROM tracked_quotes WHERE id=? AND at=?',(key,at)).fetchone()
            if prior and prior[0]!=payload: raise ValueError('quote_is_immutable')
            db.execute('INSERT OR IGNORE INTO tracked_quotes VALUES (?,?,?)',(key,at,payload))

    def report(self, *, now):
        if now.tzinfo is None: raise ValueError('aware_clock_required')
        rows=[]
        with sqlite3.connect(self.path) as db:
            for key,body in db.execute('SELECT id,payload FROM tracked_plans ORDER BY id'):
                d=json.loads(body); p=d['plan']
                plan=PaperPlan(entry=p['entry_eur'], stop=p['stop_eur'],target=p['target_eur'],
                    quantity=p['quantity'],costs_eur=p['assumed_round_trip_cost_eur'],
                    invalidation=p['invalidation'],exit_by=p['exit_by'])
                quotes=[Quote.model_validate(json.loads(r[0])['quote']) for r in
                        db.execute('SELECT payload FROM tracked_quotes WHERE id=?',(key,))]
                quotes=sorted((q for q in quotes if q.observed_at<=now),key=lambda q:q.observed_at)
                expiry=datetime.fromisoformat(p['expires_at'])
                result=replay_long(plan,quotes,decision_at=datetime.fromisoformat(d['evaluated_at']),
                                   entry_expires_at=expiry,entry_mode='breakout',exit_window_seconds=30,
                    maximum_entry_spread_bps=Decimal('20') if d.get('review_policy_version')=='paper-specialists-v3-conditional-chief' else None,
                    maximum_entry_gap_bps=Decimal('20') if d.get('review_policy_version')=='paper-specialists-v3-conditional-chief' else None)
                status=result.status
                if status=='not_filled' and result.reason=='no_observed_eligible_fill' and now<expiry:
                    status='watching'
                elif status=='unresolved' and now<plan.exit_by:
                    status='open_simulation'
                rows.append({'packet_id':key,'symbol':p['symbol'],'state':status,
                             'quote_count':len(quotes),'outcome':result.model_dump(mode='json')})
        return {'schema_version':'paper-tracking-v1','as_of':now.isoformat(),'trades':rows,
                'model_calls':0,'trade_authorized':False,
                'note':'Reference-quote simulation only. Scheduled exits use an observed bid in the final 30 seconds before the cutoff; never a later quote. Only decision-changing observations need be retained. Sampling gaps can miss triggers or stops. Missing entry or exit evidence never creates profit.'}

    def decisions(self):
        with sqlite3.connect(self.path) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM tracked_plans ORDER BY id')]

    def observe_transition(self, key, quote, *, symbol, source, now):
        """Keep immutable causal entry/invalidation/exit evidence, not every poll.

        A late observation cannot rewrite a recorded entry or exit. Repeated
        provider ticks are harmless across overlapping watcher processes.
        """
        quote = Quote.model_validate(quote.model_dump())
        before = next((r for r in self.report(now=now)['trades'] if r['packet_id']==key), None)
        if before is None: raise ValueError('unknown_plan')
        if before['state']=='closed' or (before['state']=='not_filled' and before['outcome']['reason']!='no_observed_eligible_fill'):
            return False
        with sqlite3.connect(self.path) as db:
            stored = [json.loads(r[0]) for r in db.execute('SELECT payload FROM tracked_quotes WHERE id=?',(key,))]
        if stored and quote.observed_at <= max(datetime.fromisoformat(r['quote']['observed_at']) for r in stored):
            return False
        self.observe(key,quote,symbol=symbol,source=source,now=now)
        after = next(r for r in self.report(now=now)['trades'] if r['packet_id']==key)
        if after['outcome']==before['outcome']:
            with sqlite3.connect(self.path) as db:
                db.execute('DELETE FROM tracked_quotes WHERE id=? AND at=?',
                           (key,quote.observed_at.astimezone(timezone.utc).isoformat()))
            return False
        return True


def ingest_capture(tracker, document, *, now):
    """Reuse hash-checked stock/FX observations, without extra API requests."""
    from ..market_data.stock_checks import evaluate
    checked=evaluate(document['stock_reference_checks'],now=now) if 'stock_reference_checks' in document else None
    stock_rows = checked['stocks'] if checked and checked['fx_status']=='current_indicative' and checked['market_clock']['status']=='open' else []
    from ..market_data.reference_quotes import validate_capture
    crypto_quotes = {}
    if 'reference_quote_capture' in document:
        try:crypto_quotes=validate_capture(document['reference_quote_capture'],now=now)
        except (ValueError,KeyError,TypeError,ArithmeticError):pass
    count=0
    with sqlite3.connect(tracker.path) as db:
        plans=[(key,json.loads(body)) for key,body in db.execute('SELECT id,payload FROM tracked_plans')]
    active = {r['packet_id'] for r in tracker.report(now=now)['trades']
              if r['state'] != 'closed' and r['outcome']['reason'] in
                 ('no_observed_eligible_fill', 'no_observed_exit_by_deadline')}
    for key,d in plans:
        if key not in active: continue
        if d['candidate_id'].startswith('crypto:'):
            q=crypto_quotes.get(d['plan']['symbol'])
            if q:
                quote=Quote(observed_at=q['retrieved_at'],bid=q['bid'],ask=q['ask'])
                if quote.observed_at>=datetime.fromisoformat(d['evaluated_at']):
                    count+=tracker.observe_transition(key,quote,symbol=q['symbol'],source='kraken:'+q['source_payload_sha256'],now=now)
            continue
        for row in stock_rows:
            if row['symbol']!=d['plan']['symbol'] or row['quote_status']!='current_reference_only':continue
            quote=Quote(observed_at=row['observed_at'],bid=row['indicative_bid_eur'],ask=row['indicative_ask_eur'])
            if quote.observed_at<datetime.fromisoformat(d['evaluated_at']):continue
            count+=tracker.observe_transition(key,quote,symbol=row['symbol'],source='alpaca_iex:'+document['stock_reference_checks']['payload_sha256'],now=now)
    return count


def main():
    import argparse
    from pathlib import Path
    from datetime import timezone
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal',type=Path,required=True)
    parser.add_argument('--decision',type=Path)
    parser.add_argument('--capture',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    tracker=PaperTracker(args.journal)
    if args.decision: tracker.register(json.loads(args.decision.read_text()))
    now=datetime.now(timezone.utc)
    if args.capture: ingest_capture(tracker,json.loads(args.capture.read_text()),now=now)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(tracker.report(now=now),indent=2)+'\n')


if __name__=='__main__':main()
