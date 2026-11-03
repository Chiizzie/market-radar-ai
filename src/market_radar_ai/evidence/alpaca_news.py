"""Bounded publisher-tagged news using existing Alpaca data credentials."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import requests
from .news import EvidenceItem

SCOPE = 'PUBLISHER_TAGGED_STOCK_NEWS_PARTIAL'


def validate_symbol(symbol):
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}', symbol):
        raise ValueError('invalid_symbol')


def parse_alpaca_news(payload, *, symbol, now, start):
    validate_symbol(symbol)
    if now.tzinfo is None or start.tzinfo is None or not start <= now:
        raise ValueError('invalid_time_window')
    if not isinstance(payload, dict) or not isinstance(payload.get('news'), list):
        raise ValueError('invalid_news_response')
    rows = payload['news']
    if len(rows) > 10:
        raise ValueError('news_limit_exceeded')
    items, rejected, seen = [], [], set()
    for index, row in enumerate(rows):
        try:
            tags = row['symbols']
            if not isinstance(tags, list) or len(tags) > 100:
                raise ValueError('invalid_tags')
            for tag in tags:
                validate_symbol(tag)
            if symbol not in tags:
                raise ValueError('requested_symbol_not_tagged')
            published = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))
            updated = datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00'))
            if not start <= published <= updated <= now:
                raise ValueError('invalid_article_times')
            # Provider tags establish reported relevance, not independent confirmation.
            item = EvidenceItem(kind='news', title=row['headline'], source=row['source'],
                url=row['url'], published_at=published, retrieved_at=now,
                symbols=tuple(sorted(set(tags))))
            if item.evidence_id in seen:
                raise ValueError('duplicate_url')
            seen.add(item.evidence_id)
            items.append({'evidence_id':item.evidence_id, **item.model_dump(mode='json')})
        except (ValueError, TypeError, KeyError, AttributeError):
            rejected.append({'index':index, 'reason':'invalid_unrelated_stale_or_duplicate_item'})
    return {'schema_version':'1.0', 'provider':'alpaca_news', 'scope':SCOPE,
        'query_symbol':symbol, 'status':'partial', 'retrieved_at':now.isoformat(),
        'request_start':start.isoformat(), 'request_end':now.isoformat(),
        'items':items, 'rejected':rejected, 'response_item_count':len(rows),
        'more_available':bool(payload.get('next_page_token')),
        'coverage_complete':False, 'trade_authorized':False,
        'limitations':['Publisher-reported tags; not independently confirmed',
                       'One page, ten articles and a seven-day window per stock',
                       'No complete earnings or economic event calendar']}


def fetch_alpaca_news(symbol, *, session=None, env=None,
                      clock=lambda:datetime.now(timezone.utc)):
    validate_symbol(symbol)
    now = clock()
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    start = now - timedelta(days=7)
    env = os.environ if env is None else env
    key, secret = env.get('ALPACA_API_KEY'), env.get('ALPACA_API_SECRET')
    failure = {'schema_version':'1.0', 'provider':'alpaca_news', 'scope':SCOPE,
        'query_symbol':symbol, 'status':'error', 'retrieved_at':now.isoformat(),
        'items':[], 'coverage_complete':False, 'trade_authorized':False}
    if not key or not secret:
        return {**failure, 'status':'not_configured', 'reason':'alpaca_credentials_required'}
    owned = session is None
    session = session or requests.Session()
    try:
        with session.get('https://data.alpaca.markets/v1beta1/news',
                headers={'APCA-API-KEY-ID':key, 'APCA-API-SECRET-KEY':secret},
                params={'symbols':symbol, 'start':start.isoformat(), 'end':now.isoformat(),
                        'limit':10, 'sort':'desc', 'include_content':'false'},
                timeout=(5,15), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                reason = ('access_denied' if response.status_code in (401,403) else
                          'rate_limited' if response.status_code == 429 else 'provider_http_error')
                return {**failure, 'reason':reason}
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 1_000_000:
                    raise ValueError('response_too_large')
        result = parse_alpaca_news(json.loads(body), symbol=symbol, now=now, start=start)
        result['raw_payload_sha256'] = hashlib.sha256(body).hexdigest()
        return result
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return {**failure, 'reason':'news_provider_unavailable'}
    finally:
        if owned:
            session.close()
