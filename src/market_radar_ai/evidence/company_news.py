"""Yahoo ticker-news leads via installed yfinance; not verified issuer catalysts."""
from datetime import datetime, timezone
import re
from .news import EvidenceItem


def parse_company_news(rows, *, symbol, now, limit=10):
    if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}', symbol) or now.tzinfo is None or not 1<=limit<=20:
        raise ValueError('Invalid company-news request')
    if not isinstance(rows,list):raise ValueError('Invalid news response')
    items,rejected,seen=[],[],set()
    for index,row in enumerate(rows[:limit]):
        try:
            content=row['content']
            stamp=datetime.fromisoformat(content['pubDate'].replace('Z','+00:00'))
            item=EvidenceItem(kind='news',title=content['title'],source=content['provider']['displayName'],
                url=content['canonicalUrl']['url'],published_at=stamp,retrieved_at=now,
                symbols=())
            # Requested ticker is query context, not proven article/entity relevance.
            if (now-item.published_at).total_seconds()>86400:
                rejected.append({'index':index,'reason':'stale'});continue
            if item.evidence_id in seen:
                rejected.append({'index':index,'reason':'duplicate_url'});continue
            seen.add(item.evidence_id)
            items.append({'evidence_id':item.evidence_id,**item.model_dump(mode='json')})
        except (KeyError,TypeError,ValueError,AttributeError):
            rejected.append({'index':index,'reason':'invalid_item'})
    return {'schema_version':'1.0','provider':'yahoo_ticker_news','scope':'COMPANY_NEWS_LEADS',
        'query_symbol':symbol,'status':'partial' if not rows or rejected or len(rows)>limit else 'ok',
        'response_item_count':len(rows),
        'availability_note':'empty_response_unconfirmed' if not rows else 'provider_items_received',
        'retrieved_at':now.isoformat(),'items':items,'rejected':rejected,
        'deferred':max(0,len(rows)-limit),'coverage_complete':False,'trade_authorized':False}


def fetch_company_news(symbol):
    if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}',symbol):raise ValueError('Invalid symbol')
    try:
        import yfinance as yf
        rows=yf.Ticker(symbol).get_news(count=10,tab='news')
        return parse_company_news(rows,symbol=symbol,now=datetime.now(timezone.utc))
    except Exception:
        return {'schema_version':'1.0','provider':'yahoo_ticker_news','scope':'COMPANY_NEWS_LEADS',
            'query_symbol':symbol,'status':'error','retrieved_at':datetime.now(timezone.utc).isoformat(),
            'items':[],'reason':'company_news_unavailable','coverage_complete':False,'trade_authorized':False}


def main():
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol',default='MSFT')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=fetch_company_news(args.symbol)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'query_symbol':args.symbol,'items':len(result['items'])}))
    return int(result['status']=='error')


if __name__=='__main__':raise SystemExit(main())
