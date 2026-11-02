"""Credential-free Federal Reserve announcements; macro context, not ticker news."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree
import requests
from .news import EvidenceItem

URL='https://www.federalreserve.gov/feeds/press_all.xml'


def parse_feed(body, *, now, max_age_seconds=7*86400):
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
            if urlsplit(link).hostname not in ('www.federalreserve.gov','federalreserve.gov'):
                raise ValueError('Unexpected publisher link')
            stamp=parsedate_to_datetime(row.findtext('pubDate',''))
            item=EvidenceItem(kind='news',title=row.findtext('title','').strip(),source='Federal Reserve Board',
                url=link,published_at=stamp,retrieved_at=now)
            if (now-stamp).total_seconds()>max_age_seconds:
                rejected.append({'index':index,'reason':'stale'});continue
            if item.evidence_id in seen:
                rejected.append({'index':index,'reason':'duplicate_url'});continue
            seen.add(item.evidence_id)
            items.append({'evidence_id':item.evidence_id,**item.model_dump(mode='json')})
        except (ValueError,TypeError,OverflowError):
            rejected.append({'index':index,'reason':'invalid_item'})
    return {'schema_version':'1.0','provider':'federal_reserve_rss','scope':'MACRO_ANNOUNCEMENTS_ONLY',
        'status':'partial' if rejected or len(rows)>50 else 'ok','retrieved_at':now.isoformat(),
        'items':items,'rejected':rejected,'deferred':max(0,len(rows)-50),
        'coverage_complete':False,'trade_authorized':False}


def fetch_feed(session=None):
    session=session or requests.Session()
    try:
        with session.get(URL,timeout=(5,15),allow_redirects=False,stream=True) as response:
            if response.status_code!=200:raise ValueError('HTTP failure')
            body=bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body)>2_000_000:raise ValueError('Feed too large')
        return parse_feed(body,now=datetime.now(timezone.utc))
    except (requests.RequestException,ValueError,ElementTree.ParseError):
        return {'schema_version':'1.0','provider':'federal_reserve_rss','scope':'MACRO_ANNOUNCEMENTS_ONLY',
            'status':'error','retrieved_at':datetime.now(timezone.utc).isoformat(),
            'items':[],'reason':'public_feed_unavailable','coverage_complete':False,'trade_authorized':False}


def main():
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=fetch_feed()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'items':len(result['items']),
                      'rejected':len(result.get('rejected',[]))}))
    return int(result['status']=='error')


if __name__=='__main__':raise SystemExit(main())
