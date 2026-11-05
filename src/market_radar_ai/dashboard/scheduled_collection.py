"""One bounded scheduled capture; original evidence timestamps, no AI or orders."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .collection_schedule import scheduled_scope, collection_window
from .evidence import export_evidence
from .snapshot_delivery import deliver
from ..evidence.earnings_calendar import CalendarCapture

STOCKS = ('NVDA', 'MSFT', 'AAPL', 'AMD', 'META', 'AMZN', 'GOOGL', 'TSLA', 'MU')
CRYPTO = ('XBTEUR', 'ETHEUR', 'SOLEUR', 'XRPEUR')
TTL_SECONDS = 900
MAX_CACHE_BYTES = 2_000_000


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def validate_evidence(news, calendars, now, stocks=STOCKS):
    export_evidence(news, now=now)
    if not isinstance(calendars, list) or len(calendars) != len(stocks):
        raise ValueError('cached_calendar_count')
    seen = set()
    for record in calendars:
        payload = record['payload']
        if digest(payload) != record['payload_sha256']:
            raise ValueError('cached_calendar_checksum')
        parsed = CalendarCapture.model_validate(payload)
        if parsed.symbol not in stocks or parsed.symbol in seen or parsed.retrieved_at > now:
            raise ValueError('cached_calendar_identity_or_clock')
        seen.add(parsed.symbol)


def load_cache(path, now, stocks=STOCKS):
    """Corrupt, future and expired caches cause a fresh collection, never redating."""
    try:
        if path.stat().st_size > MAX_CACHE_BYTES:
            return None
        cache = json.loads(path.read_text())
        payload = cache['payload']
        if cache['sha256'] != digest(payload) or payload['version'] != 1:
            return None
        if payload['stocks'] != list(stocks):
            return None
        collected = datetime.fromisoformat(payload['collection_started_at'])
        if collected.tzinfo is None or not 0 <= (now-collected).total_seconds() < TTL_SECONDS:
            return None
        validate_evidence(payload['news'], payload['calendars'], now, stocks)
        return payload
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temp.replace(path)


def run_stage(module, args):
    # No shell, no retries, and only fixed module names supplied below.
    return subprocess.run([sys.executable, '-m', 'market_radar_ai.'+module, *map(str, args)],
                          timeout=240, check=False).returncode


def run_cycle(*, env, output, cache_path, clock=lambda: datetime.now(timezone.utc),
              run=run_stage, delivery=deliver):
    started = clock()
    if not scheduled_scope(env, started):
        raise ValueError('scheduled_collection_scope_or_window_invalid')
    if any(env.get(k) for k in ('OPENAI_API_KEY', 'OPEN_API_KEY', 'GH_BUDGET_TOKEN')):
        raise ValueError('paid_credentials_forbidden_in_scheduled_collection')
    output.mkdir(parents=True, exist_ok=True)
    discovery = None
    stocks = STOCKS
    if env.get('ENABLE_STOCK_DISCOVERY') == 'true':
        from ..market_data.discovery import discover
        discovery = discover(env=env, now=started, fallback=STOCKS)
        stocks = tuple(discovery['selected_symbols'])
        write_json(output/'discovery.json', discovery)
    # User watchlist supplements rotating discovery, without replacing its candidates.
    stocks = tuple(dict.fromkeys([*stocks, 'MU']))
    if env.get('GH_PAPER_TOKEN'):
        from ..agents.github_paper_tracking import update
        prior = update(env['GH_PAPER_TOKEN'], now=started)
        active = [r['symbol'] for r in prior['trades'] if r['state'] in ('watching', 'open_simulation')]
        # Keep watched symbols in the quote batch even when discovery rotates.
        if len(set(active)) > 20:
            raise RuntimeError('paper_tracking_capacity_exceeded')
        stocks = tuple(dict.fromkeys([*active, *stocks]))[:20]
    cache = load_cache(cache_path, started, stocks)
    stages = {}

    def stage(label, module, args, file):
        code = run(module, args)
        stages[label] = 'ok' if code == 0 else 'failed'
        if not file.is_file():
            raise RuntimeError('collector_output_missing:'+label)

    news = output/'news.json'
    if cache:
        write_json(news, cache['news'])
    else:
        stage('news', 'evidence.scanner_feed', ['--output', news, '--company-provider',
              'alpaca', '--symbols', *stocks], news)
    capture = output/'capture.json'
    stage('market', 'market_data.capture', ['--output', capture, '--stock-provider',
          'alpaca_iex', '--stocks', *stocks, '--crypto', *CRYPTO], capture)
    context = output/'context-capture.json'
    stage('context', 'market_data.stock_context', ['--capture', capture, '--output', context], context)
    quotes = output/'quote-capture.json'
    enriched = output/'enriched-capture.json'
    if cache:
        doc = json.loads(context.read_text())
        doc['earnings_calendars'] = cache['calendars']
        write_json(enriched, doc)
    else:
        stage('calendar', 'evidence.earnings_calendar', ['--capture', context, '--output', enriched], enriched)
        feed, doc = json.loads(news.read_text()), json.loads(enriched.read_text())
        validate_evidence(feed, doc['earnings_calendars'], clock(), stocks)
        payload = {'version': 1, 'stocks': list(stocks), 'collection_started_at': started.isoformat(),
                   'news': feed, 'calendars': doc['earnings_calendars']}
        write_json(cache_path, {'payload': payload, 'sha256': digest(payload)})
    if env.get('ENABLE_STOCK_CHECKS') == 'true':
        checked = output/'checked-capture.json'
        stage('stock_checks', 'market_data.stock_checks', ['--capture', enriched, '--output', checked], checked)
        write_json(enriched, json.loads(checked.read_text()))
    # Collect short-lived crypto references after slow calendar/catalogue work.
    stage('quotes', 'market_data.reference_quotes', ['--capture', enriched, '--output', quotes], quotes)
    write_json(enriched, json.loads(quotes.read_text()))
    from ..agents.early_screening import screen
    write_json(output/'early-screening.json', screen(json.loads(enriched.read_text()), now=clock()))
    if env.get('GH_PAPER_TOKEN'):
        from ..agents.github_paper_tracking import update
        doc = json.loads(enriched.read_text())
        report = update(env['GH_PAPER_TOKEN'], now=clock(), capture=doc)
        write_json(output/'paper-tracking.json', report)
        doc['paper_tracking_report'] = report
        write_json(enriched, doc)
    for label, module, name in (
        ('context_packages', 'agents.context_packages', 'context-packages.json'),
        ('readiness', 'market_data.readiness', 'readiness.json'),
        ('qualification', 'agents.qualification', 'qualification.json'),
        ('paper_packets', 'agents.paper_verdict', 'paper-review-packets.json'),
        ('dashboard', 'dashboard.export', 'dashboard.json'),
    ):
        path = output/name
        stage(label, module, ['--capture', enriched, '--evidence', news, '--output', path], path)
    receipt = delivery(json.loads(enriched.read_text()), env=env, clock=clock,
                       evidence=json.loads(news.read_text()))
    write_json(output/'delivery.json', receipt)
    feed, doc = json.loads(news.read_text()), json.loads(enriched.read_text())
    failed = [k for k, v in stages.items() if v == 'failed']
    if feed['status'] in ('error', 'not_configured'):
        failed.append('news_unavailable')
    if any(r['payload']['status'] in ('error', 'not_configured') for r in doc['earnings_calendars']):
        failed.append('calendar_unavailable')
    gaps = [c['requested_symbol'] for c in doc.get('captures', []) if not c['payload']['quality_passed_at_capture']]
    report = {'state': 'delivered_with_failures' if failed else 'delivered_with_data_gaps' if gaps else 'delivered',
              'unusable_or_stale_symbols': gaps,
              'started_at': started.isoformat(), 'delivery': receipt, 'stages': stages,
              'evidence_cache': 'reused_original_timestamps' if cache else 'collected',
              'evidence_collection_started_at': cache['collection_started_at'] if cache else started.isoformat(),
              'failures': failed, 'target_interval_seconds': 300, 'model_calls': 0,
              'trade_authorized': False, 'stock_discovery': discovery}
    write_json(output/'collection-report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/scheduled'))
    parser.add_argument('--cache', type=Path, default=Path('.scanner-cache/evidence.json'))
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    # Clock-closed cron jobs do no network work, even if a runner started late.
    if not collection_window(now) and os.environ.get('GITHUB_EVENT_NAME') == 'schedule':
        print(json.dumps({'state': 'outside_collection_window', 'model_calls': 0}))
        return 0
    from .collection_notification import notify
    try:
        result = run_cycle(env=os.environ, output=args.output, cache_path=args.cache)
    except Exception:
        try:
            receipt = notify({'state':'failed'}, env=os.environ, clock=lambda: datetime.now(timezone.utc))
            write_json(args.output/'collection-notification.json', receipt)
        except Exception:
            print('Collection failure notification unavailable; inspect run logs.')
        raise
    receipt = notify(result, env=os.environ, clock=lambda: datetime.now(timezone.utc))
    write_json(args.output/'collection-notification.json', receipt)
    print(json.dumps(result))
    return int(bool(result['failures']))


if __name__ == '__main__':
    raise SystemExit(main())
