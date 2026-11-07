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
from ..market_data.limits import STOCK_RESEARCH_LIMIT, CRYPTO_RESEARCH_LIMIT
from ..market_data.crypto_identities import ASSETS

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


def write_json(path, value, *, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=None if compact else 2,
                              separators=(',', ':') if compact else None)+'\n')
    temp.replace(path)


def run_stage(module, args):
    # No shell, no retries, and only fixed module names supplied below.
    return subprocess.run([sys.executable, '-m', 'market_radar_ai.'+module, *map(str, args)],
                          timeout=240, check=False).returncode


def run_cycle(*, env, output, cache_path, clock=lambda: datetime.now(timezone.utc),
              run=run_stage, delivery=deliver, stock_symbols=None, crypto_symbols=None):
    started = clock()
    if not scheduled_scope(env, started):
        raise ValueError('scheduled_collection_scope_or_window_invalid')
    if any(env.get(k) for k in ('OPENAI_API_KEY', 'OPEN_API_KEY', 'GH_BUDGET_TOKEN')):
        raise ValueError('paid_credentials_forbidden_in_scheduled_collection')
    output.mkdir(parents=True, exist_ok=True)
    discovery = None
    crypto_discovery = None
    crypto = CRYPTO
    if crypto_symbols is not None:
        if (not 1<=len(crypto_symbols)<=CRYPTO_RESEARCH_LIMIT or len(set(crypto_symbols))!=len(crypto_symbols)
                or any(p not in ASSETS for p in crypto_symbols)):
            raise ValueError('invalid_targeted_crypto_pairs')
        crypto=tuple(crypto_symbols)
    active_crypto = []
    stock_limit = STOCK_RESEARCH_LIMIT if env.get('ENABLE_BROAD_DISCOVERY')=='true' else 20
    stocks = STOCKS
    if stock_symbols is not None:
        from ..market_data.discovery import SYMBOL
        if not 1 <= len(stock_symbols) <= STOCK_RESEARCH_LIMIT or len(set(stock_symbols)) != len(stock_symbols) or any(not isinstance(s,str) or not SYMBOL.fullmatch(s) for s in stock_symbols):
            raise ValueError('invalid_targeted_stock_symbols')
        stocks = tuple(stock_symbols)
        stock_limit = max(stock_limit,len(stocks))
    if stock_symbols is None and env.get('ENABLE_STOCK_DISCOVERY') == 'true':
        from ..market_data.discovery import discover
        discovery = discover(env=env, now=started, fallback=STOCKS,
                             universe_cache_path=cache_path.with_name('discovery-universe.json'))
        stocks = tuple(discovery['selected_symbols'])
    # User watchlist supplements rotating discovery, without replacing its candidates.
    if stock_symbols is None:
        stocks = tuple(dict.fromkeys([*stocks, 'MU']))
    if env.get('GH_PAPER_TOKEN'):
        from ..agents.github_paper_tracking import update
        prior = update(env['GH_PAPER_TOKEN'], now=started)
        active_rows = [r['symbol'] for r in prior['trades'] if r['state'] in ('watching', 'open_simulation')]
        active = [s for s in active_rows if s not in ASSETS]
        active_crypto = [s for s in active_rows if s in ASSETS]
        # Keep watched symbols in the quote batch even when discovery rotates.
        if len(set(active)) > stock_limit or len(set(active_crypto)) > CRYPTO_RESEARCH_LIMIT:
            raise RuntimeError('paper_tracking_capacity_exceeded')
        stocks = tuple(dict.fromkeys([*active, *stocks]))[:stock_limit]
    if env.get('ENABLE_CRYPTO_DISCOVERY') == 'true' and stock_symbols is None and crypto_symbols is None:
        from ..market_data.crypto_discovery import discover as discover_crypto
        crypto_discovery = discover_crypto(now=clock(),active=active_crypto)
        crypto = tuple(crypto_discovery['selected_pairs']) or tuple(dict.fromkeys([*active_crypto,*CRYPTO]))
        write_json(output/'crypto-discovery.json',crypto_discovery)
    else:
        crypto = tuple(dict.fromkeys([*active_crypto,*crypto]))
    if discovery is not None:
        # The journal can displace rotating candidates. Report what will really
        # be researched, retaining the original discovery shortlist separately.
        discovery['collection_selected_symbols'] = list(stocks)
        discovery['displaced_symbols'] = [s for s in discovery['selected_symbols'] if s not in stocks]
        for row in discovery.get('selection_manifest', []):
            selected = row['symbol'] in stocks
            if row['detail_selected'] and not selected:
                row['selection_reason'] = 'displaced_by_active_paper_watch'
            elif selected and not row['detail_selected']:
                row['selection_reason'] = 'active_watch_or_user_watchlist'
            row['detail_selected'] = selected
        if 'coverage' in discovery:
            if 'candidate_pool_symbols' in discovery:
                pool = set(discovery['candidate_pool_symbols'])
            elif discovery.get('universe'):
                pool = set(discovery['universe']['symbols'])
            else:
                pool = set(discovery['deferred_symbols'])
                if not discovery['fallback_used']:
                    pool.update(discovery['selected_symbols'])
            discovery['coverage']['research_selected'] = len(pool.intersection(stocks))
            discovery['coverage']['research_deferred'] = len(pool.difference(stocks))
            discovery['deferred_symbols'] = sorted(pool.difference(stocks))
        if discovery.get('selection_manifest'):
            from collections import Counter
            manifest = discovery.pop('selection_manifest')
            discovery['selection_reason_counts'] = dict(Counter(r['selection_reason'] for r in manifest))
            discovery['selection_manifest_file'] = 'discovery-selection.json'
            write_json(output/'discovery-selection.json', {
                'schema_version': 'stock-selection-trace-v1', 'observed_at': started.isoformat(),
                'selection_policy': discovery['selection_policy'], 'symbols': manifest,
                'trade_authorized': False,
                'note': 'Discovery scores are not trade admission. Current daily-bar volume is compared with the previous daily bar, not historical same-time volume. Unavailable acceleration is not zero.'}, compact=True)
        write_json(output/'discovery.json', discovery)
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
          'alpaca_iex', '--per-market-limit', str(max(stock_limit,len(crypto))), '--stocks', *stocks, '--crypto', *crypto], capture)
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
    catalogued = output/'crypto-catalogue-capture.json'
    if crypto_discovery and crypto_discovery.get('catalogue'):
        doc=json.loads(enriched.read_text())
        doc['crypto_catalogue']=crypto_discovery['catalogue']
        write_json(catalogued,doc)
    else:
        stage('crypto_catalogue', 'market_data.crypto_checks', ['--capture', enriched, '--output', catalogued], catalogued)
    write_json(enriched, json.loads(catalogued.read_text()))
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
    # Existing repository token reads accounting only; no model credentials or calls.
    from .api_budget import read_summary
    doc = json.loads(enriched.read_text())
    doc['api_budget'] = read_summary(env.get('GH_PAPER_TOKEN'), clock=clock)
    if discovery is not None or crypto_discovery is not None:
        from .discovery_coverage import build_coverage
        doc['discovery_coverage'] = build_coverage(discovery,crypto_discovery,doc,now=clock())
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
    context_gaps = [r['payload']['symbol'] for r in doc.get('stock_context', [])
                    if any(r['payload'][k]['status'] == 'unavailable' for k in ('daily', 'intraday'))]
    report = {'state': 'delivered_with_failures' if failed else 'delivered_with_data_gaps' if gaps or context_gaps else 'delivered',
              'unusable_or_stale_symbols': gaps,
              'context_unavailable_symbols': context_gaps,
              'started_at': started.isoformat(), 'delivery': receipt, 'stages': stages,
              'evidence_cache': 'reused_original_timestamps' if cache else 'collected',
              'evidence_collection_started_at': cache['collection_started_at'] if cache else started.isoformat(),
              'failures': failed, 'target_interval_seconds': 300, 'model_calls': 0,
              'trade_authorized': False, 'stock_discovery': discovery,'crypto_discovery':crypto_discovery}
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
