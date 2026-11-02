"""Public Europe support-list discovery; not account-level eligibility evidence."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import requests


class _SupportList(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heading = self.item = None
        self.active = False
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag == 'h2': self.heading = []
        if tag == 'li' and self.active: self.item = []

    def handle_data(self, data):
        if self.heading is not None: self.heading.append(data)
        if self.item is not None: self.item.append(data)

    def handle_endtag(self, tag):
        if tag == 'h2' and self.heading is not None:
            self.active = ' '.join(''.join(self.heading).split()).lower() == 'supported crypto'
            self.heading = None
        if tag == 'li' and self.item is not None:
            self.items.append(''.join(self.item).strip())
            self.item = None


def parse_supported_crypto(html):
    parser = _SupportList()
    parser.feed(html)
    records = []
    for item in parser.items:
        match = re.fullmatch(r'(.+?)\s*\(([A-Z0-9]+)\)', item)
        if not match:
            raise ValueError('Robinhood support-list structure changed')
        records.append({'name': match[1].strip(), 'symbol': match[2]})
    if not records or len({r['symbol'] for r in records}) != len(records):
        raise ValueError('Empty or ambiguous Robinhood support list')
    return records


class RobinhoodEuropeCatalogue:
    URL = 'https://robinhood.com/eu/en/support/articles/about-robinhood-crypto/'

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def fetch(self):
        response = self.session.get(self.URL, timeout=15, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError('robinhood_support_page_unavailable')
        return {'source': self.URL, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'public_europe_support_list_not_account_verification',
                'assets': parse_supported_crypto(response.text)}
