"""Bounded public publisher feeds; research context, never trade authorization."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree
import requests
from .news import EvidenceItem

URL='https://www.federalreserve.gov/feeds/press_all.xml'
FEEDS = {
    'fed': dict(url=URL, provider='federal_reserve_rss', scope='MACRO_ANNOUNCEMENTS_ONLY',
                publisher='Federal Reserve Board', hosts=('www.federalreserve.gov', 'federalreserve.gov'), symbols=()),
    'microsoft': dict(url='https://news.microsoft.com/source/feed/', provider='microsoft_source_rss',
                scope='SINGLE_ISSUER_EDITORIAL_NEWS', publisher='Microsoft Source', hosts=('news.microsoft.com',), symbols=()),
    'nvidia': dict(url='https://nvidianews.nvidia.com/releases.xml', provider='nvidia_newsroom_rss',
                scope='SINGLE_ISSUER_EDITORIAL_NEWS', publisher='NVIDIA Newsroom',
                hosts=('nvidianews.nvidia.com', 'blogs.nvidia.com'), symbols=('NVDA',)),
}


def parse_feed(body, *, now, max_age_seconds=7*86400, publisher="Federal Reserve Board", hosts=("www.federalreserve.gov","federalreserve.gov"), provider="federal_reserve_rss", scope="MACRO_ANNOUNCEMENTS_ONLY", symbols=()):
    if now.tzinfo is None or max_age_seconds<=0:
        raise ValueError('Aware clock and positive age required')
    if len(body)>2_000_000:
        raise ValueError('Feed too large')
    text=body.decode('utf-8-sig')
    if '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML declarations not permitted')
    root=ElementTree.fromstring(text)
    if root.tag!='rss' or root.find('channel') is None:
        raise ValueError('Unsupported feed schema')
    rows=root.findall('./channel/item')
    items, rejected, seen=[],[],set()
    for index,row in enumerate(rows[:50]):
        try:
            link=row.findtext('link','').strip()
            if urlsplit(link).hostname not in hosts:
                raise ValueError('Unexpected publisher link')
            stamp=parsedate_to_datetime(row.findtext('pubDate',''))
            item=EvidenceItem(kind='news',title=row.findtext('title','').strip(),source=publisher,
                url=link,published_at=stamp,retrieved_at=now,symbols=symbols)
            if (now-stamp).total_seconds()>max_age_seconds:
                rejected.append({'index':index,'reason':'stale'});continue
            if item.evidence_id in seen:
                rejected.append({'index':index,'reason':'duplicate_url'});continue
            seen.add(item.evidence_id)
            items.append({'evidence_id':item.evidence_id,**item.model_dump(mode='json')})
        except (ValueError,TypeError,OverflowError):
            rejected.append({'index':index,'reason':'invalid_item'})
    return {'schema_version':'1.0','provider':provider,'scope':scope,
        'status':'partial' if rejected or len(rows)>50 else 'ok','retrieved_at':now.isoformat(),
        'items':items,'rejected':rejected,'deferred':max(0,len(rows)-50),
        'coverage_complete':False,'trade_authorized':False}


def _fetch_feed_once(session=None, *, issuer=False, source=None):
    if issuer and source is not None:
        raise ValueError('Select one source')
    selected = source or ('microsoft' if issuer else 'fed')
    if selected not in FEEDS:
        raise ValueError('Unknown feed source')
    config = FEEDS[selected]
    provider, scope, url = config['provider'], config['scope'], config['url']
    session=session or requests.Session()
    reason = "transport_error"
    http_status = None
    try:
        with session.get(url,timeout=(5,15),allow_redirects=False,stream=True) as response:
            http_status = response.status_code
            if http_status != 200:
                reason = 'redirect_not_followed' if 300 <= http_status < 400 else 'http_error'
                raise ValueError('HTTP failure')
            reason = 'body_read_error'
            body=bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body)>2_000_000:
                    reason = 'response_too_large'
                    raise ValueError('Feed too large')
        reason = 'invalid_feed'
        return parse_feed(body,now=datetime.now(timezone.utc),provider=provider,scope=scope,
            publisher=config['publisher'], hosts=config['hosts'], symbols=config['symbols'])
    except (requests.RequestException,ValueError,ElementTree.ParseError):
        return {'schema_version':'1.0','provider':provider,'scope':scope,
            'status':'error','retrieved_at':datetime.now(timezone.utc).isoformat(),
            'items':[],'reason':reason,'http_status':http_status,'coverage_complete':False,'trade_authorized':False}


def fetch_feed(session=None, *, issuer=False, source=None):
    """At most two public reads; retry only a transport failure, never HTTP errors."""
    result=_fetch_feed_once(session,issuer=issuer,source=source)
    attempts=[{'status':result['status'],'reason':result.get('reason')}]
    if result.get('status')=='error' and result.get('reason')=='transport_error':
        result=_fetch_feed_once(session,issuer=issuer,source=source)
        attempts.append({'status':result['status'],'reason':result.get('reason')})
    return {**result,'fetch_attempts':attempts}


def main():
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument("--source",choices=tuple(FEEDS))
    selection.add_argument("--issuer",action="store_true",help="Use the allowlisted Microsoft Source feed")
    args=parser.parse_args()
    result=fetch_feed(issuer=args.issuer,source=args.source)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'items':len(result['items']),
                      'rejected':len(result.get('rejected',[])),
                      'reason':result.get('reason'),'http_status':result.get('http_status')}))
    return int(result['status']=='error')


if __name__=='__main__':raise SystemExit(main())
