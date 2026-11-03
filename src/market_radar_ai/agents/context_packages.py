"""All-session research packages; no minimum intraday bar count or trade plan."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from .candidate_packages import canonical, digest
from .roles import AgentRole
from ..dashboard.evidence import export_evidence
from ..market_data.models import Candle


def build_context_packages(document, feed, *, now):
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    records = document.get('stock_context', [])
    if not isinstance(records, list) or len(records)>20:
        raise ValueError('context_capture_limit')
    try:
        news = export_evidence(feed,now=now)
    except (ValueError,TypeError,KeyError,AttributeError):
        news = {'status':'error','items':[]}
    allowed = {c['requested_symbol'] for c in document['captures'] if c['market']=='stocks'}
    local = now.astimezone(ZoneInfo('America/New_York'))
    minute = local.hour*60+local.minute
    phase = ('WEEKEND_CONTEXT' if local.weekday()>=5 else
             'PREMARKET_CONTEXT' if minute<570 else
             'OPENING_CONTEXT' if minute<670 else
             'INTRADAY_CONTEXT' if minute<960 else 'AFTER_HOURS_CONTEXT')
    packages, seen = [], set()
    for record in records:
        p = record['payload']
        if digest(p)!=record['payload_sha256']:
            raise ValueError('context_checksum_mismatch')
        symbol=p['symbol']
        if symbol not in allowed or symbol in seen:
            raise ValueError('context_identity_invalid')
        seen.add(symbol)
        if (p['schema_version']!='stock-context-capture-v1' or p['provider']!='alpaca_iex'
                or p['native_currency']!='USD' or p['trade_authorized'] is not False):
            raise ValueError('context_source_invalid')
        retrieved=datetime.fromisoformat(p['retrieved_at'])
        if not 0 <= (now-retrieved).total_seconds() <= 900:
            continue
        if p['status'] not in ('received','partial'):
            raise ValueError('context_status_invalid')
        bars={}
        for kind, interval, limit in (('daily','1d',10),('intraday','5m',24)):
            section=p[kind]
            if section['status'] not in ('received','empty','window_not_started','unavailable'):
                raise ValueError('context_section_invalid')
            rows=[Candle.model_validate(row) for row in section['bars']]
            if len(rows)>limit or (section['status']=='received') != bool(rows):
                raise ValueError('context_bars_invalid')
            start,end=datetime.fromisoformat(section['request_start']),datetime.fromisoformat(section['request_end'])
            if end>retrieved or end>now or (retrieved-end).total_seconds()>300:
                raise ValueError('context_request_time_invalid')
            previous=None
            for c in rows:
                if (c.symbol!=symbol or c.source!='alpaca_iex' or c.quote_currency!='USD'
                        or c.interval!=interval or not start <= c.timestamp <= end
                        or (previous and c.timestamp<=previous)
                        or not all(v.is_finite() for v in (c.open,c.high,c.low,c.close,c.volume))):
                    raise ValueError('context_bar_identity_or_time_invalid')
                day=c.timestamp.astimezone(ZoneInfo('America/New_York')).date()
                end_day=end.astimezone(ZoneInfo('America/New_York')).date()
                if kind=='daily' and not 0 < (end_day-day).days <=21:
                    raise ValueError('context_daily_window_invalid')
                if kind=='intraday' and (day!=end_day or c.timestamp+timedelta(minutes=5)>end):
                    raise ValueError('context_intraday_window_invalid')
                previous=c.timestamp
            bars[kind]=[c.model_dump(mode='json') for c in rows]
        source={**p, 'original_context_sha256':record['payload_sha256'],
                'use':'CONTEXT_ONLY_NOT_EXECUTABLE', 'session_phase_by_clock':phase,
                'phase_is_exchange_calendar_verified':False}
        sources={'context:'+digest(source):source}
        news_ids=[]
        macro_ids=[]
        if news['status'] in ('ok','partial'):
            linked=[x for x in news['items'] if symbol in x['symbols']
                and 0 <= (now-datetime.fromisoformat(x['retrieved_at'])).total_seconds() <=900
                and 0 <= (now-datetime.fromisoformat(x['published_at'])).total_seconds() <=7*86400]
            for item in sorted(linked,key=lambda x:x['published_at'],reverse=True)[:5]:
                sid='news:'+digest(item)
                if sid not in sources:
                    sources[sid]=item;news_ids.append(sid)
            macro=[x for x in news['items'] if x['source']=='Federal Reserve Board'
                and urlsplit(x['url']).hostname in ('federalreserve.gov','www.federalreserve.gov')
                and 0 <= (now-datetime.fromisoformat(x['retrieved_at'])).total_seconds() <=900
                and 0 <= (now-datetime.fromisoformat(x['published_at'])).total_seconds() <=7*86400]
            for item in sorted(macro,key=lambda x:x['published_at'],reverse=True)[:3]:
                sid='news:'+digest(item)
                if sid not in sources:
                    sources[sid]=item;macro_ids.append(sid)
        if not bars['daily'] and not bars['intraday'] and not news_ids and not macro_ids:
            continue
        gaps=['broker_account_eligibility_unverified','executable_quotes_and_costs_missing',
            'eur_trade_plan_missing','fresh_fx_conversion_missing','independent_catalyst_confirmation_missing',
            'exchange_session_not_verified','iex_limited_market_coverage','six_agent_review_not_run',
            'context_is_not_trade_admission','corporate_actions_not_verified','complete_event_calendar_missing']
        if not bars['daily']:gaps.append('prior_session_history_missing')
        if not bars['intraday']:gaps.append('current_session_bars_missing')
        elif (now-datetime.fromisoformat(bars['intraday'][-1]['timestamp'])).total_seconds()>900:
            gaps.append('latest_context_bar_stale_for_trading')
        if not news_ids:gaps.append('symbol_linked_news_missing')
        if now.astimezone(ZoneInfo('Europe/Dublin')).hour>=22:gaps.append('entry_cutoff_reached')
        calendar_ids=[]
        if 'earnings_calendars' in document:
            from ..evidence.earnings_calendar import calendar_source
            calendar=calendar_source(document,symbol,now=now)
            if calendar:
                sid='calendar:'+digest(calendar)
                sources[sid]=calendar;calendar_ids.append(sid)
                if calendar['events']:gaps.append('reported_earnings_require_issuer_confirmation')
                else:gaps.append('earnings_calendar_no_confirmed_event')
            else:gaps.append('earnings_calendar_missing_or_stale')
        expiry=min(now+timedelta(minutes=5),retrieved+timedelta(minutes=15))
        for sid in news_ids+macro_ids+calendar_ids:
            expiry=min(expiry,datetime.fromisoformat(sources[sid]['retrieved_at'])+timedelta(minutes=15))
        if expiry<=now:continue
        body={'schema_version':'context-evidence-package-v1','candidate_id':'stocks:'+symbol,
            'symbol':symbol,'market':'stocks','research_mode':phase,'assembled_at':now.isoformat(),
            'expires_at':expiry.isoformat(),'native_currency':'USD','reporting_currency':'EUR',
            'eur_conversion':'not_supplied','sources':sources,'source_ids':list(sources),
            'news_source_ids':news_ids,'macro_source_ids':macro_ids,
            'context_only_news_ids':[sid for sid in news_ids+macro_ids if not sources[sid]['intraday_recent']],
            'missing_evidence':gaps,'roles':[r.value for r in AgentRole],
            'research_questions':['What changed since the prior session?',
                'Which sourced catalysts could affect the opening or the rest of today?',
                'Which bullish and bearish scenarios need fresh confirmation?',
                'What evidence would invalidate each scenario?'],
            'constraints':{'maximum_planned_loss_eur':'20','entry_cutoff':'22:00',
                'timezone':'Europe/Dublin','overnight_allowed':False},
            'usage_note':'Historical and extended-hours context only. Do not predict the opening as fact, infer missing news, compare incomplete daily volume, or treat this as executable evidence.',
            'review_status':'NOT_RUN','model_calls':0,'trade_authorized':False,'plan':None}
        if 'earnings_calendars' in document:
            body['calendar_source_ids']=calendar_ids
        packages.append({'package_id':digest(body),'package':body})
    return {'schema_version':'context-package-batch-v1','assembled_at':now.isoformat(),
            'packages':packages,'model_calls':0,'trade_authorized':False}


def main():
    import argparse,json
    from pathlib import Path
    from datetime import timezone
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.capture.stat().st_size>4_000_000 or args.evidence.stat().st_size>2_000_000:
        raise ValueError('input_too_large')
    result=build_context_packages(json.loads(args.capture.read_text()),json.loads(args.evidence.read_text()),now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'context_packages':len(result['packages']),'model_calls':0,'trade_authorized':False}))


if __name__=='__main__':main()
