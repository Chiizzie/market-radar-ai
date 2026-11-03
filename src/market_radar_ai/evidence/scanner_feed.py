"""Bounded stock/macro news leads for the manual scanner; never clears trade gates."""
from datetime import datetime, timezone
from .company_news import fetch_company_news
from .public_feed import fetch_feed
from .combine import combine_feeds

COMPANY_SYMBOLS = ('NVDA', 'MSFT', 'AAPL')
PUBLIC_SOURCES = ('fed', 'microsoft', 'nvidia')


def collect(*, company_fetch=fetch_company_news, public_fetch=fetch_feed,
            clock=lambda: datetime.now(timezone.utc)):
    feeds = []
    for kind, names in (('company', COMPANY_SYMBOLS), ('publisher', PUBLIC_SOURCES)):
        for name in names:
            try:
                feed = company_fetch(name) if kind == 'company' else public_fetch(source=name)
            except Exception:
                feed = {'status': 'error', 'items': [], 'scope': 'UNAVAILABLE',
                        'retrieved_at': clock().isoformat()}
            feeds.append(feed)
    result = combine_feeds(feeds, now=clock())
    result['scope'] = 'BOUNDED_STOCK_AND_MACRO_LEADS_NO_CRYPTO_COVERAGE'
    result['limitations'] = [
        'Company query is not verified article relevance',
        'Publisher articles are not a complete scheduled-event calendar',
        'No crypto news coverage in this collector',
        'News arrival does not verify broker eligibility or execution costs',
        'Disclosures do not identify real-time trader orders',
    ]
    return result


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'items': len(result['items']),
                      'sources': result['sources'], 'trade_authorized': False}))
    return int(result['status'] == 'error')


if __name__ == '__main__':
    raise SystemExit(main())
