"""Allowlisted evidence projection; feed health is separate from article age."""
from datetime import datetime
from ..evidence.news import EvidenceItem


def export_evidence(feed, *, now):
    if now.tzinfo is None:
        raise ValueError('Aware clock required')
    if feed is None:
        return {'schema_version':'1.0','status':'not_connected','items':[],
                'scope':'UNKNOWN','coverage_complete':False}
    if not isinstance(feed,dict) or feed.get('status') not in ('ok','partial','error','not_configured'):
        raise ValueError('Invalid evidence feed')
    status=feed['status']
    if status in ('error','not_configured'):
        return {'schema_version':'1.0','status':status,'items':[],
                'scope':feed.get('scope','UNSPECIFIED'),'coverage_complete':False}
    stamp=datetime.fromisoformat(feed['retrieved_at'])
    if stamp.tzinfo is None or stamp>now:
        raise ValueError('Invalid evidence retrieval time')
    rows=feed['items']
    if not isinstance(rows,list) or len(rows)>50:
        raise ValueError('Invalid evidence count')
    items=[]
    for row in rows:
        fields={k:v for k,v in row.items() if k in EvidenceItem.model_fields}
        item=EvidenceItem.model_validate(fields)
        if item.retrieved_at>now:
            raise ValueError('Future evidence retrieval')
        items.append({'evidence_id':item.evidence_id,**item.model_dump(mode='json'),
            'publication_age_seconds':(now-item.published_at).total_seconds(),
            'intraday_recent':0 <= (now-item.published_at).total_seconds() <= 3600})
    return {'schema_version':'1.0','status':'stale' if (now-stamp).total_seconds()>900 else status,
        'scope':feed.get('scope','UNSPECIFIED'),'retrieved_at':stamp.isoformat(),
        'coverage_complete':False,'items':items}
