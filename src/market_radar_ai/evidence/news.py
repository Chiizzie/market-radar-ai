"""Bounded Alpha Vantage news ingestion; credentials remain server-side."""
from datetime import datetime, timezone
import hashlib
import os
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
import requests
from pydantic import BaseModel, AwareDatetime, ConfigDict, Field, model_validator


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    kind: Literal['news', 'scheduled_catalyst', 'investor_disclosure']
    title: str = Field(min_length=1,max_length=1000)
    source: str = Field(min_length=1,max_length=200)
    url: str
    published_at: AwareDatetime
    retrieved_at: AwareDatetime
    event_at: AwareDatetime | None = None
    symbols: tuple[str,...] = ()
    verification: Literal['provider_reported'] = 'provider_reported'

    @model_validator(mode='after')
    def check(self):
        url=urlsplit(self.url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('HTTPS source URL required')
        if self.published_at > self.retrieved_at:
            raise ValueError('Publication is in the future')
        if self.kind=='investor_disclosure' and self.event_at and self.event_at > self.published_at:
            raise ValueError('Disclosure cannot precede reported transaction')
        return self

    @property
    def evidence_id(self):
        u=urlsplit(self.url)
        canonical=urlunsplit((u.scheme,u.netloc.lower(),u.path,u.query,''))
        return hashlib.sha256(canonical.encode()).hexdigest()


def parse_news(payload, *, now, max_age_seconds=86400, limit=50):
    if now.tzinfo is None or not 1 <= limit <= 100 or max_age_seconds <= 0:
        raise ValueError('Invalid ingestion bounds')
    if not isinstance(payload,dict) or not isinstance(payload.get('feed'),list):
        raise ValueError('News unavailable or malformed')
    items, rejected, seen = [], [], set()
    feed=payload['feed']
    for index, row in enumerate(feed[:limit]):
        try:
            stamp=datetime.strptime(row['time_published'],'%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
            item=EvidenceItem(kind='news',title=row['title'],source=row['source'],url=row['url'],
                published_at=stamp,retrieved_at=now,
                symbols=tuple(sorted({r['ticker'] for r in row.get('ticker_sentiment',[])})))
            if (now-stamp).total_seconds()>max_age_seconds:
                rejected.append({'index':index,'reason':'stale'});continue
            if item.evidence_id in seen:
                rejected.append({'index':index,'reason':'duplicate_url'});continue
            seen.add(item.evidence_id)
            items.append({'evidence_id':item.evidence_id,**item.model_dump(mode='json')})
        except (ValueError,TypeError,KeyError):
            rejected.append({'index':index,'reason':'invalid_item'})
    return {'schema_version':'1.0','status':'partial' if rejected or len(feed)>limit else 'ok',
        'provider':'alpha_vantage','retrieved_at':now.isoformat(),'items':items,
        'rejected':rejected,'deferred':max(0,len(feed)-limit),
        'coverage_complete':False,'trade_authorized':False}


class NewsProvider:
    def __init__(self, api_key=None, session=None):
        self.key=api_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        self.session=session or requests.Session()

    def fetch(self, *, symbol=None):
        now=datetime.now(timezone.utc)
        if not self.key:
            return {'schema_version':'1.0','status':'not_configured','items':[],
                    'trade_authorized':False,'reason':'server_side_news_key_required'}
        params={'function':'NEWS_SENTIMENT','sort':'LATEST','limit':50,'apikey':self.key}
        if symbol:
            import re
            if not re.fullmatch(r'(CRYPTO:)?[A-Z0-9.\-]{1,15}',symbol):
                raise ValueError('Invalid provider symbol')
            params['tickers']=symbol
        try:
            with self.session.get('https://www.alphavantage.co/query',params=params,
                    timeout=(5,15),allow_redirects=False,stream=True) as response:
                if response.status_code!=200:raise ValueError('Provider failure')
                body=bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>2_000_000:raise ValueError('Response too large')
            import json
            return parse_news(json.loads(body),now=datetime.now(timezone.utc))
        except (requests.RequestException, ValueError):
            # Never expose request URLs or exceptions containing API credentials.
            return {'schema_version':'1.0','status':'error','items':[],
                    'trade_authorized':False,'reason':'news_provider_unavailable'}
