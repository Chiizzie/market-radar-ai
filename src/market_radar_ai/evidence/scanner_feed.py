"""Bounded stock/macro news leads for the manual scanner; never clears trade gates."""
from ..market_data.limits import STOCK_RESEARCH_LIMIT
from datetime import datetime, timezone
from .company_news import fetch_company_news
from .public_feed import fetch_feed
from .combine import combine_feeds

COMPANY_SYMBOLS = ('NVDA', 'MSFT', 'AAPL')
PUBLIC_SOURCES = ('fed', 'microsoft', 'nvidia')


def collect(*, company_fetch=fetch_company_news, public_fetch=fetch_feed,
            crypto_fetch=None, company_symbols=COMPANY_SYMBOLS,
            clock=lambda: datetime.now(timezone.utc)):
    import re
    if not 1 <= len(company_symbols) <= STOCK_RESEARCH_LIMIT or any(not isinstance(s,str) or not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}',s) for s in company_symbols):
        raise ValueError('invalid_company_symbols')
    feeds = []
    from concurrent.futures import ThreadPoolExecutor
    jobs=[('company',s) for s in dict.fromkeys(company_symbols)]+[('publisher',s) for s in PUBLIC_SOURCES]
    def fetch_one(job):
        kind,name=job
        try:
            return company_fetch(name) if kind=='company' else public_fetch(source=name)
        except Exception:
            return {'status':'error','items':[],'scope':'UNAVAILABLE','retrieved_at':clock().isoformat()}
    with ThreadPoolExecutor(max_workers=4) as executor:
        feeds.extend(executor.map(fetch_one,jobs))
    if crypto_fetch is not None:
        try:
            feeds.append(crypto_fetch())
        except Exception:
            feeds.append({'status':'error','items':[], 'scope':'CRYPTO_NEWS_UNAVAILABLE',
                          'retrieved_at':clock().isoformat()})
    result = combine_feeds(feeds, now=clock())
    result['scope'] = 'BOUNDED_STOCK_AND_MACRO_LEADS_NO_CRYPTO_COVERAGE'
    result['limitations'] = [
        'Company query is not verified article relevance',
        'Publisher articles are not a complete scheduled-event calendar',
        'No crypto news coverage in this collector',
        'News arrival does not verify broker eligibility or execution costs',
        'Disclosures do not identify real-time trader orders',
    ]
    if crypto_fetch is not None:
        result['scope'] = 'BOUNDED_STOCK_MACRO_AND_PUBLISHER_TAGGED_CRYPTO_NEWS'
        result['limitations'][2] = 'Crypto relevance uses explicit publisher tags; one publisher is not independent confirmation'
    return result


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--symbols', nargs='+', default=list(COMPANY_SYMBOLS))
    parser.add_argument('--company-provider', choices=('yahoo', 'alpaca'), default='yahoo')
    args = parser.parse_args()
    from .crypto_feed import fetch_crypto_feed
    from .alpaca_news import fetch_alpaca_news
    result = collect(crypto_fetch=fetch_crypto_feed,company_symbols=args.symbols,
                     company_fetch=fetch_alpaca_news if args.company_provider=='alpaca' else fetch_company_news)
    result['company_provider'] = args.company_provider
    if args.company_provider == 'alpaca':
        result['limitations'][0] = 'Stock relevance uses explicit provider tags; one publisher is not independent confirmation'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'items': len(result['items']),
                      'sources': result['sources'], 'trade_authorized': False}))
    return int(result['status'] == 'error')


if __name__ == '__main__':
    raise SystemExit(main())
