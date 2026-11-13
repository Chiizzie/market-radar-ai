"""Durable, independent observations for the paired entry-confirmation trial."""
import argparse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
import json
import os
import re
import time
from .candidate_packages import canonical, digest
from .comparison_live import EventClient, envelope, event_id
from .paper_comparison import aware
from .paper_outcomes import Quote
from .strategy_experiment import build, num, NY
from .strategy_experiment_live import prepare, StrategyObserver
from .entry_confirmation import (
    ARMS, VARIANT, PROTOCOL, PROTOCOL_ID, common, outcomes, build_report,
)


class EntryExperiment:
    def __init__(self, root, *, client, clock=lambda: datetime.now(UTC), day=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.journal = self.root/'events.jsonl'
        if self.journal.exists():
            raise ValueError('fresh_entry_projection_required')
        self.client, self.clock = client, clock
        self.day = day or clock().date().isoformat()
        self.cursor = 0
        self.seen, self.cohorts, self.quotes, self.source = set(), {}, [], []
        self.screen = None
        self.health = {'polls': 0, 'quotes_received': 0, 'error_polls': 0,
                       'maximum_poll_gap_seconds': 0, 'capacity_deferred': 0,
                       'model_calls': 0}
        self.last_poll = None

    def apply(self, event):
        if event['event_id'] in self.seen:
            return
        if (event['experiment_id'] != PROTOCOL_ID or event['day'] != self.day
                or event_id(PROTOCOL_ID, event) != event['event_id']):
            raise ValueError('entry_event_identity')
        p, at = json.loads(event['payload_json']), aware(event['occurred_at'])
        if (p.get('protocol_id') != PROTOCOL_ID or p.get('dataset_kind') != 'forward'
                or p.get('trade_authorized') is not False or p.get('model_calls') != 0
                or p.get('shadow_only') is not True or self.day < PROTOCOL['commissioning_from']):
            raise ValueError('entry_event_scope')
        kind = event['kind']
        if kind == 'method_enrol':
            if p.get('schema_version') != 'entry-confirmation-enrol-v1':
                raise ValueError('entry_enrol_schema')
            s = build(p['inputs'], now=at)
            if s != p['cohort'] or s['blockers'] or s['setup_id'] != p['setup_id']:
                raise ValueError('entry_cohort_replay_mismatch')
            old = self.cohorts.get(s['setup_id'])
            if old is not None and {k:v for k,v in old.items() if k!='enrolled_at'} != s:
                raise ValueError('entry_cohort_conflict')
            self.cohorts.setdefault(s['setup_id'], {
                **s, 'enrolled_at': max(at, aware(event['received_at'])).isoformat()})
            if len(self.cohorts) > PROTOCOL['maximum_cohorts_per_day']:
                raise ValueError('entry_cohort_capacity')
        elif kind == 'quote':
            q = Quote.model_validate(p['quote'])
            received = aware(p['received_at'])
            if (received != at or not 0 <= (received-q.observed_at).total_seconds() <= 30
                    or q.bid > q.ask or not re.fullmatch(r'alpaca_iex:[a-f0-9]{64}', p['source'])):
                raise ValueError('entry_quote_invalid')
            matches = [c for c in self.cohorts.values() if c['candidate_id'] == p['candidate_id']]
            if not matches:
                raise ValueError('entry_quote_without_cohort')
            fx = num(p['eur_per_usd'])
            expected = num(matches[0]['variants'][VARIANT]['plan']['fx_rate'])
            native = p['native_quote_usd']
            if (fx != expected or q.bid != num(native['bid'])*fx or q.ask != num(native['ask'])*fx):
                raise ValueError('entry_quote_currency_mismatch')
            self.quotes.append({**p, 'durable_received_at': event['received_at']})
        elif kind == 'audit':
            if (p.get('schema_version') != 'entry-confirmation-report-v1'
                    or p.get('protocol') != PROTOCOL or p['evaluation_day'] != self.day
                    or aware(p['as_of']) != at):
                raise ValueError('entry_report_identity')
        else:
            raise ValueError('entry_event_kind')
        self.seen.add(event['event_id'])
        if kind != 'audit':
            self.source.append(event)
        with self.journal.open('a') as f:
            f.write(canonical(event)+'\n')

    def sync(self):
        start = time.monotonic()
        for _ in range(250):
            page = self.client.read(PROTOCOL_ID, self.day, self.cursor)
            if not page['events']:
                return
            for event in page['events']:
                if type(event['seq']) is not int or event['seq'] <= self.cursor:
                    raise ValueError('entry_event_order')
                self.apply(event)
                self.cursor = event['seq']
            if page['next'] != self.cursor:
                raise ValueError('entry_cursor_mismatch')
            if len(self.source)>100000 or self.journal.stat().st_size>75_000_000 or time.monotonic()-start>90:
                raise ValueError('entry_restore_capacity')
        raise ValueError('entry_page_capacity')

    def outcomes(self, now):
        by_symbol = {}
        for q in self.quotes:
            by_symbol.setdefault(q['candidate_id'], []).append(q)
        return {key: outcomes(c, by_symbol.get(c['candidate_id'], []), now)
                for key,c in self.cohorts.items()}

    def active(self, now):
        # Do not stop observing because the ask-trigger control has exited.
        return [self.cohorts[key] for key,pair in self.outcomes(now).items()
                if any(r['state'] in ('watching','open') for r in pair.values())]

    def enrol(self, inputs, *, capture_sha, source_failures=()):
        self.sync()
        now = self.clock()
        active, events = len(self.active(now)), []
        rows, known = list(source_failures), set(self.cohorts)
        for source in inputs:
            s = build(source, now=now)
            blocks = s['blockers'][:]
            if not blocks and s['setup_id'] in known:
                blocks = ['already_frozen_this_session']
            if not blocks and len(known) >= PROTOCOL['maximum_cohorts_per_day']:
                blocks = ['daily_cohort_capacity']
            if not blocks and active >= PROTOCOL['maximum_active_symbols']:
                blocks = ['observer_capacity_deferred']
                self.health['capacity_deferred'] += 1
            if not blocks:
                payload = {**common(), 'schema_version': 'entry-confirmation-enrol-v1',
                           'setup_id': s['setup_id'], 'inputs': source, 'cohort': s}
                e = envelope('method_enrol', payload, now)
                if len(e['payload_json'].encode()) > 175000:
                    blocks = ['source_event_capacity']
                else:
                    events.append(e)
                    known.add(s['setup_id'])
                    active += not s['variants'][VARIANT]['blockers']
            detail = blocks or s['variants'][VARIANT]['blockers']
            rows.append({'candidate_id': 'stocks:'+source['symbol'], 'blockers': detail})
        batch, size = [], 0
        for e in events:
            n = len(canonical(e).encode())
            if batch and (size+n>1_500_000 or len(batch)>=30):
                self.client.append(PROTOCOL_ID, batch)
                batch, size = [], 0
            batch.append(e)
            size += n
        if batch:
            self.client.append(PROTOCOL_ID, batch)
        self.sync()
        self.screen = {'as_of': self.clock().isoformat(), 'examined': len(rows),
                       'enrolled': len(events), 'capture_sha256': capture_sha,
                       'reasons': dict(Counter(b for row in rows for b in row['blockers'])),
                       'rows': rows}

    def poll(self, observer):
        self.sync()
        now = self.clock()
        if self.last_poll:
            self.health['maximum_poll_gap_seconds'] = max(
                self.health['maximum_poll_gap_seconds'], (now-self.last_poll).total_seconds())
        self.last_poll = now
        active = sorted(self.active(now), key=lambda c:(c['enrolled_at'], c['setup_id']))
        self.health['capacity_deferred'] += max(0, len(active)-40)
        observations, failures = observer.fetch(active[:40]) if active else ([], [])
        events = [envelope('quote', {**o, **common()}, aware(o['received_at'])) for o in observations]
        if events:
            self.client.append(PROTOCOL_ID, events)
            self.sync()
        self.health['polls'] += 1
        self.health['quotes_received'] += len(events)
        self.health['error_polls'] += bool(failures)
        self.health['last_active_symbols'] = len(active)
        self.health['last_success_at'] = self.clock().isoformat()
        if failures:
            self.health['last_errors'] = sorted(set(failures))[:10]

    def close(self):
        self.sync()
        report = build_report(self, self.clock())
        (self.root/'report.json').write_text(canonical(report)+'\n')
        self.client.append(PROTOCOL_ID, [envelope('audit', report, aware(report['as_of']))])
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('capture','news','history'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('artifacts/entry-confirmation'))
    parser.add_argument('--duration', type=int, default=330)
    a = parser.parse_args()
    if not 1 <= a.duration <= 360:
        raise ValueError('bounded_entry_duration')
    if any(os.environ.get(k) for k in ('OPENAI_API_KEY','OPEN_API_KEY','TELEGRAM_BOT_TOKEN',
                                       'GH_PAPER_TOKEN','GH_BUDGET_TOKEN')):
        raise ValueError('unneeded_credentials_forbidden')
    clock = lambda: datetime.now(UTC)
    local = clock().astimezone(NY)
    if (clock().date().isoformat() < PROTOCOL['commissioning_from'] or local.weekday()>4
            or not (9,35) <= (local.hour,local.minute) <= (16,5)):
        print(json.dumps({'state':'outside_entry_experiment_window','model_calls':0}))
        return 0
    def read(path, limit):
        if path.stat().st_size > limit:
            raise ValueError('entry_input_capacity')
        return json.loads(path.read_text())
    capture, news = read(a.capture,12_000_000), read(a.news,8_000_000)
    cache = read(a.history,6_000_000) if a.history.is_file() else {}
    worker = EntryExperiment(a.output, client=EventClient(os.environ.get('REVIEW_INGEST_SECRET')), clock=clock)
    start = time.monotonic()
    worker.sync()
    worker.health['startup_seconds'] = round(time.monotonic()-start,3)
    inputs, failures = prepare(capture,news,cache,env=os.environ,clock=clock)
    worker.enrol(inputs,capture_sha=digest(capture),source_failures=failures)
    observer = StrategyObserver(os.environ,clock=clock)
    end = time.monotonic()+a.duration
    while time.monotonic() < end:
        tick = time.monotonic()
        worker.poll(observer)
        (a.output/'worker-health.json').write_text(canonical(worker.health)+'\n')
        remaining = end-time.monotonic()
        if remaining>0:
            time.sleep(min(remaining,max(.1,5-(time.monotonic()-tick))))
    report = worker.close()
    print(json.dumps({'state':'entry_confirmation_published','protocol_id':PROTOCOL_ID,
                      'phase':report['phase'],'cohorts':report['cohort_count'],
                      'polls':worker.health['polls'],'error_polls':worker.health['error_polls'],
                      'model_calls':0,'trade_authorized':False}))
    if worker.health['error_polls']:
        print('::warning::Entry experiment quote gaps remain visible; comparison may be incomplete.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
