"""Bounded Finnhub earnings dates; provider reports, never trade admission."""
from ..market_data.limits import STOCK_RESEARCH_LIMIT
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import re
from typing import Literal
from zoneinfo import ZoneInfo
import requests
from pydantic import BaseModel, ConfigDict, AwareDatetime, Field, model_validator
from ..agents.candidate_packages import digest


class EarningsEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    symbol: str = Field(pattern=r'^[A-Z][A-Z0-9.\-]{0,14}$')
    date: date
    session_hint: Literal['bmo','amc','dmh','unknown']
    exact_time: None = None
    date_timezone: Literal['provider_unspecified'] = 'provider_unspecified'
    verification: Literal['provider_reported_not_issuer_confirmed'] = 'provider_reported_not_issuer_confirmed'


class CalendarCapture(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal['earnings-calendar-capture-v1'] = 'earnings-calendar-capture-v1'
    provider: Literal['finnhub'] = 'finnhub'
    symbol: str = Field(pattern=r'^[A-Z][A-Z0-9.\-]{0,14}$')
    retrieved_at: AwareDatetime
    request_from: date
    request_to: date
    status: Literal['received','empty','partial','error','not_configured']
    events: list[EarningsEvent] = Field(default_factory=list,max_length=20)
    rejected_count: int = Field(default=0,ge=0,le=20)
    reason: Literal['credentials_required','authentication_failed','access_denied','rate_limited',
                    'provider_http_error','provider_unavailable'] | None = None
    raw_payload_sha256: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    coverage_complete: Literal[False] = False
    trade_authorized: Literal[False] = False

    @model_validator(mode='after')
    def validate_capture(self):
        if not 0 <= (self.request_to-self.request_from).days <= 15:
            raise ValueError('invalid_calendar_window')
        if self.status in ('received','empty','partial'):
            if not self.raw_payload_sha256 or self.reason is not None:
                raise ValueError('calendar_provenance_missing')
            if (self.status=='received' and not self.events) or (self.status=='empty' and self.events):
                raise ValueError('calendar_status_mismatch')
        elif self.events or self.reason is None:
            raise ValueError('calendar_failure_mismatch')
        seen=set()
        for event in self.events:
            if event.symbol != self.symbol or not self.request_from <= event.date <= self.request_to:
                raise ValueError('calendar_identity_or_date_mismatch')
            key=(event.date,event.session_hint)
            if key in seen:raise ValueError('duplicate_event')
            seen.add(key)
        return self


def parse_calendar(data, *, symbol, now, start, end, raw_digest):
    if not isinstance(data,dict) or not isinstance(data.get('earningsCalendar'),list):
        raise ValueError('invalid_calendar_response')
    rows=data['earningsCalendar']
    if len(rows)>20:raise ValueError('calendar_limit_exceeded')
    events=[];rejected=0;seen=set()
    for row in rows:
        try:
            if row['symbol']!=symbol:raise ValueError('symbol_mismatch')
            day=date.fromisoformat(row['date'])
            if not start<=day<=end:raise ValueError('date_outside_window')
            hour=row.get('hour') or 'unknown'
            event=EarningsEvent(symbol=symbol,date=day,session_hint=hour)
            key=(day,hour)
            if key in seen:raise ValueError('duplicate_event')
            seen.add(key);events.append(event)
        except (ValueError,TypeError,KeyError):rejected+=1
    return CalendarCapture(symbol=symbol,retrieved_at=now,request_from=start,request_to=end,
        status='partial' if rejected else 'received' if events else 'empty',
        events=events,rejected_count=rejected,raw_payload_sha256=raw_digest)


def fetch_calendar(symbol, *, env=None, session=None, clock=lambda:datetime.now(timezone.utc)):
    if not isinstance(symbol,str) or not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}',symbol):
        raise ValueError('invalid_symbol')
    now=clock()
    if now.tzinfo is None:raise ValueError('aware_clock_required')
    day=now.astimezone(ZoneInfo('America/New_York')).date()
    start,end=day-timedelta(days=1),day+timedelta(days=14)
    fields=dict(symbol=symbol,retrieved_at=now,request_from=start,request_to=end)
    key=(os.environ if env is None else env).get('FINNHUB_API_KEY')
    if not key:return CalendarCapture(**fields,status='not_configured',reason='credentials_required')
    owned=session is None;session=session or requests.Session()
    try:
        # Official client uses token authentication; never persist request URL or errors.
        with session.get('https://api.finnhub.io/api/v1/calendar/earnings',
                params={'token':key,'symbol':symbol,'from':start.isoformat(),'to':end.isoformat(),
                        'international':'false'},timeout=(5,15),allow_redirects=False,stream=True) as response:
            if response.status_code!=200:
                reason={401:'authentication_failed',403:'access_denied',429:'rate_limited'}.get(response.status_code,'provider_http_error')
                return CalendarCapture(**fields,status='error',reason=reason)
            body=bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body)>1_000_000:raise ValueError('calendar_response_too_large')
        return parse_calendar(json.loads(body),symbol=symbol,now=now,start=start,end=end,
                              raw_digest=hashlib.sha256(body).hexdigest())
    except (requests.RequestException,ValueError,TypeError,KeyError):
        return CalendarCapture(**fields,status='error',reason='provider_unavailable')
    finally:
        if owned:session.close()


def enrich(document, *, fetch=fetch_calendar):
    result=deepcopy(document)
    symbols=list(dict.fromkeys(c['requested_symbol'] for c in document['captures'] if c['market']=='stocks'))
    if len(symbols)>STOCK_RESEARCH_LIMIT:raise ValueError('calendar_symbol_limit')
    result['earnings_calendars']=[]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        for capture in executor.map(fetch,symbols):
            payload=capture.model_dump(mode='json')
            result['earnings_calendars'].append({'payload':payload,'payload_sha256':digest(payload)})
    return result


def calendar_source(document, symbol, *, now):
    records=document.get('earnings_calendars',[])
    if not isinstance(records,list) or len(records)>STOCK_RESEARCH_LIMIT:raise ValueError('calendar_record_limit')
    seen=set();selected=None
    allowed={c['requested_symbol'] for c in document['captures'] if c['market']=='stocks'}
    for record in records:
        p=record['payload']
        if digest(p)!=record['payload_sha256']:raise ValueError('calendar_checksum_mismatch')
        capture=CalendarCapture.model_validate(p)
        if capture.symbol in seen or capture.symbol not in allowed:raise ValueError('calendar_identity_mismatch')
        seen.add(capture.symbol)
        age=(now-capture.retrieved_at).total_seconds()
        if age<0:raise ValueError('future_calendar_retrieval')
        if capture.symbol==symbol and age<=900:
            selected={**capture.model_dump(mode='json'),'original_calendar_sha256':record['payload_sha256'],
                'use':'CALENDAR_CONTEXT_ONLY',
                'interpretation':'Dates and session hints are provider reports; exact time and issuer confirmation are unknown. Empty results do not prove no event. Estimates and results are intentionally omitted because currency is unspecified.'}
    return selected


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.capture.stat().st_size>4_000_000:raise ValueError('input_too_large')
    result=enrich(json.loads(args.capture.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    records=[r['payload'] for r in result['earnings_calendars']]
    print(json.dumps({'calendars':[{'symbol':r['symbol'],'status':r['status'],'events':len(r['events']),'reason':r['reason']} for r in records],
                      'model_calls':0,'trade_authorized':False}))
    return int(any(r['status'] in ('error','not_configured') for r in records))


if __name__=='__main__':raise SystemExit(main())
