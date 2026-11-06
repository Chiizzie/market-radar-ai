"""Compact factual context for the protected dashboard; no model conclusions."""
from ..market_data.limits import STOCK_RESEARCH_LIMIT
from ..agents.context_packages import build_context_packages


def build_briefing(document, evidence, *, now):
    batch=build_context_packages(document,evidence,now=now)
    rows=[]
    for record in batch['packages']:
        p=record['package']
        context=next(s for sid,s in p['sources'].items() if sid.startswith('context:'))
        daily=context['daily']['bars'];intraday=context['intraday']['bars']
        calendars=[p['sources'][sid] for sid in p.get('calendar_source_ids',[])]
        c=calendars[0] if calendars else None
        rows.append({'symbol':p['symbol'],'phase':p['research_mode'],
            'context_retrieved_at':context['retrieved_at'],'expires_at':p['expires_at'],
            'daily_bars':len(daily),'intraday_bars':len(intraday),
            'latest_daily_at':daily[-1]['timestamp'] if daily else None,
            'latest_intraday_at':intraday[-1]['timestamp'] if intraday else None,
            'news_evidence_ids':[p['sources'][sid]['evidence_id'] for sid in p['news_source_ids']],
            'calendar':None if c is None else {k:c[k] for k in
                ('provider','status','retrieved_at','request_from','request_to','events','reason','coverage_complete')},
            'missing_evidence':p['missing_evidence'],
            'review_status':'NOT_RUN','trade_authorized':False})
    attempted=sum(c['market']=='stocks' for c in document['captures'])
    if len(rows)>STOCK_RESEARCH_LIMIT or len(rows)>attempted:raise ValueError('briefing_coverage_invalid')
    return {'schema_version':'research-briefing-v1','assembled_at':batch['assembled_at'],
        'scope':'REQUESTED_STOCKS_ONLY','stocks_attempted':attempted,
        'stocks_with_context':len(rows),'stocks_without_context':attempted-len(rows),
        'rows':rows,'model_calls':0,'trade_authorized':False}
