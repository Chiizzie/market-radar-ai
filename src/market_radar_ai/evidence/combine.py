"""Combine validated feeds without hiding source failures or refreshing timestamps."""
from ..dashboard.evidence import export_evidence


def combine_feeds(feeds, *, now):
    if not 1 <= len(feeds) <= 24:
        raise ValueError('Supply one to twenty-four feeds')
    sources, items, seen = [], [], set()
    rejected = []
    for index, feed in enumerate(feeds):
        try:
            validated=export_evidence(feed,now=now)
        except (ValueError,TypeError,KeyError,AttributeError):
            validated={'status':'error','scope':'UNKNOWN','items':[]}
        sources.append({'source_index':index,'status':validated['status'],
            'scope':validated['scope'],'retrieved_at':validated.get('retrieved_at'),
            'validated_item_count':len(validated['items']),
            'query_symbol':feed.get('query_symbol') if isinstance(feed,dict) else None})
        if validated['status'] not in ('ok','partial'):
            continue
        for item in validated['items']:
            if item['evidence_id'] in seen:
                rejected.append({'source_index':index,'reason':'duplicate_url'});continue
            seen.add(item['evidence_id'])
            items.append(item)
    from datetime import datetime
    items.sort(key=lambda i:datetime.fromisoformat(i['published_at']),reverse=True)
    deferred=max(0,len(items)-50)
    good=[s for s in sources if s['status'] in ('ok','partial')]
    # Oldest contributing retrieval prevents aggregation from refreshing old data.
    from datetime import datetime
    retrieved=min((datetime.fromisoformat(s['retrieved_at']) for s in good),default=now)
    status=('error' if not good else 'partial' if rejected or deferred or any(s['status']!='ok' for s in sources) else 'ok')
    return {'schema_version':'1.0','provider':'combined_evidence','scope':'MIXED_RESEARCH_LEADS',
        'status':status,'retrieved_at':retrieved.isoformat(),'sources':sources,
        'items':items[:50],'rejected':rejected,'deferred':deferred,
        'coverage_complete':False,'trade_authorized':False}


def main():
    import argparse,json
    from pathlib import Path
    from datetime import datetime,timezone
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feeds',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    feeds=[]
    for path in args.feeds:
        try:feeds.append(json.loads(path.read_text()))
        except (OSError,ValueError):feeds.append({'status':'error','items':[]})
    result=combine_feeds(feeds,now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'items':len(result['items']),'sources':result['sources']}))


if __name__=='__main__':main()
