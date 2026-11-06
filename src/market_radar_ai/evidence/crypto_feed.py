"""Public publisher-tagged crypto news. No title-based asset inference."""
from datetime import datetime, timezone
from xml.etree import ElementTree
from urllib.parse import urlsplit
import requests
from .public_feed import parse_feed

URL = 'https://www.coindesk.com/arc/outboundfeeds/rss'
TAGS = {'bitcoin':'BTC', 'btc':'BTC', 'ethereum':'ETH', 'eth':'ETH',
        'solana':'SOL', 'sol':'SOL', 'xrp':'XRP', 'bitcoin news':'BTC',
        'ethereum news':'ETH', 'solana news':'SOL', 'xrp news':'XRP'}
from ..market_data.crypto_identities import ASSETS
PAIR_ASSETS = {pair:asset[0] for pair,asset in ASSETS.items()}
# Full exact publisher categories only for additional assets; short/common-word
# tickers are deliberately not interpreted as asset identity.
for asset, name in ASSETS.values():
    if len(name)>3 and name.casefold() not in {'near', 'render', 'sky', 'optimism', 'sandbox', 'quant'}:
        TAGS.setdefault(name.casefold(), asset)
        TAGS.setdefault(name.casefold()+' news', asset)


def matches(item, pair):
    asset = PAIR_ASSETS.get(pair)
    return bool(asset and item['source'] == 'CoinDesk'
        and urlsplit(item['url']).hostname in ('coindesk.com', 'www.coindesk.com')
        and 'COINDESK:'+asset in item['symbols'] and item['kind'] == 'news')


def parse_crypto_feed(body, *, now):
    # Shared parser bounds bytes/items, rejects XML entities and foreign URLs,
    # validates publication/retrieval timestamps and deduplicates source URLs.
    result = parse_feed(body, now=now, publisher='CoinDesk',
        hosts=('coindesk.com','www.coindesk.com'), provider='coindesk_rss',
        scope='PUBLISHER_TAGGED_CRYPTO_NEWS_PARTIAL')
    root = ElementTree.fromstring(body.decode('utf-8-sig'))
    associations = {}
    for row in root.findall('./channel/item')[:50]:
        url = row.findtext('link', '').strip()
        tags = [c.text.strip().casefold() for c in row.findall('category') if c.text]
        associations.setdefault(url, sorted({'COINDESK:'+TAGS[t] for t in tags if t in TAGS}))
    for item in result['items']:
        item['symbols'] = associations.get(item['url'], [])
    # A single publisher is always partial, even if its HTTP response is complete.
    result['status'] = 'partial'
    result['identity_basis'] = 'Exact publisher category tags; not headline/query inference'
    result['limitations'] = ['One publisher only; no independent catalyst confirmation',
                            'Untagged articles remain unassociated research leads']
    return result


def _fetch_once(*, session=None, clock=lambda:datetime.now(timezone.utc)):
    reason, status = 'transport_error', None
    try:
        with (session or requests).get(URL, timeout=(5,15), allow_redirects=False, stream=True) as response:
            status = response.status_code
            if response.status_code != 200:
                reason = 'http_error'
                raise ValueError('http_failure')
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body)>2_000_000:
                    reason = 'body_too_large'
                    raise ValueError('body_too_large')
        reason = 'invalid_feed'
        return parse_crypto_feed(bytes(body), now=clock())
    except (requests.RequestException, ValueError, ElementTree.ParseError):
        return {'schema_version':'1.0','provider':'coindesk_rss',
                'scope':'PUBLISHER_TAGGED_CRYPTO_NEWS_PARTIAL','status':'error',
                'retrieved_at':clock().isoformat(),'items':[],
                'reason':reason,'http_status':status,'coverage_complete':False,'trade_authorized':False}


def fetch_crypto_feed(*, session=None, clock=lambda:datetime.now(timezone.utc)):
    result = _fetch_once(session=session,clock=clock)
    attempts = [{'status':result['status'],'reason':result.get('reason')}]
    if result.get('reason')=='transport_error':
        result = _fetch_once(session=session,clock=clock)
        attempts.append({'status':result['status'],'reason':result.get('reason')})
    return {**result,'fetch_attempts':attempts}
