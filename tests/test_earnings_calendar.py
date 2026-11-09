from datetime import timedelta
import json
import pytest
from market_radar_ai.evidence.earnings_calendar import fetch_calendar, enrich, calendar_source
from market_radar_ai.agents.context_packages import build_context_packages
from market_radar_ai.agents.candidate_review import run, reproduce
from test_stock_context import NOW, document
from test_candidate_review import answer


def response():
    return {'earningsCalendar':[{'symbol':'MSFT','date':NOW.date().isoformat(),
        'hour':'amc','epsEstimate':1.5,'revenueEstimate':123456789}]}


class Session:
    def __init__(self,data=None,status=200,body=None):self.data=response() if data is None else data;self.status=status;self.body=body;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs));outer=self
        class Response:
            status_code=outer.status
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,*args):yield outer.body if outer.body is not None else json.dumps(outer.data).encode()
        return Response()


def fetch(session=None,env=None):
    return fetch_calendar('MSFT',session=session or Session(),env={'FINNHUB_API_KEY':'private-test'} if env is None else env,clock=lambda:NOW)


def enriched(capture=None):
    return enrich(document(),fetch=lambda _:capture or fetch())


def test_bounded_request_original_dates_no_invented_time_currency_or_key():
    s=Session();r=fetch(s);url,k=s.calls[0]
    assert len(s.calls)==1 and url=='https://api.finnhub.io/api/v1/calendar/earnings'
    assert not k['allow_redirects'] and k['timeout']==(5,15) and k['stream']
    assert k['params']['from']=='2026-11-03' and k['params']['to']=='2026-11-18'
    data=r.model_dump(mode='json')
    assert data['events'][0]['session_hint']=='amc' and data['events'][0]['exact_time'] is None
    assert 'epsEstimate' not in str(data) and 'private-test' not in str(data)
    assert not r.coverage_complete and not r.trade_authorized


def test_calendar_reaches_all_six_roles_debate_and_conclusion_and_reproduces():
    d=enriched();record=build_context_packages(d,None,now=NOW)['packages'][0]
    p=record['package'];sid=p['calendar_source_ids'][0]
    assert p['sources'][sid]['events'][0]['symbol']=='MSFT'
    assert 'complete_event_calendar_missing' in p['missing_evidence']
    assert 'reported_earnings_require_issuer_confirmation' in p['missing_evidence']
    stages=[]
    def ask(stage,payload,schema):
        assert sid in payload['snapshot']['source_ids']
        stages.append(stage);return answer(stage,payload,schema)
    result=run(record,d,None,ask,clock=lambda:NOW)
    assert len(stages)==8 and result['trade_authorized'] is False
    assert reproduce(json.loads(json.dumps(record)),d,None,now=NOW)['symbol']=='MSFT'


@pytest.mark.parametrize('hour',[None,'','bmo','dmh'])
def test_missing_or_coarse_hours_preserve_uncertainty(hour):
    d=response();d['earningsCalendar'][0]['hour']=hour
    event=fetch(Session(d)).events[0]
    assert event.session_hint==(hour or 'unknown') and event.exact_time is None


@pytest.mark.parametrize('field,value',[('symbol','AAPL'),('date','2026-12-30'),('date','invalid'),('hour','16:30')])
def test_invalid_unrelated_and_out_of_range_rows_are_partial(field,value):
    d=response();d['earningsCalendar'][0][field]=value
    r=fetch(Session(d));assert r.status=='partial' and not r.events and r.rejected_count==1


def test_empty_calendar_never_proves_no_event():
    r=fetch(Session({'earningsCalendar':[]}));assert r.status=='empty'
    p=build_context_packages(enriched(r),None,now=NOW)['packages'][0]['package']
    assert 'earnings_calendar_no_confirmed_event' in p['missing_evidence']
    assert not p['trade_authorized']


@pytest.mark.parametrize('code,reason',[(401,'authentication_failed'),(403,'access_denied'),(429,'rate_limited'),(302,'provider_http_error')])
def test_access_failures_survive_as_unknown_calendar_context(code,reason):
    r=fetch(Session(status=code));assert r.status=='error' and r.reason==reason
    source=calendar_source(enriched(r),'MSFT',now=NOW)
    assert source['reason']==reason and not source['events']


def test_no_keys_or_invalid_symbol_do_not_send_requests():
    s=Session();assert fetch(s,env={}).status=='not_configured' and not s.calls
    with pytest.raises(ValueError):fetch_calendar('../MSFT',session=s,env={})
    assert not s.calls


@pytest.mark.parametrize('body',[b'x'*1_000_001,b'not json',b'{"error":"private-test"}',b'{"earningsCalendar":null}'])
def test_bad_responses_are_safe_failures(body):
    r=fetch(Session(body=body));assert r.status=='error' and 'private-test' not in r.model_dump_json()


def test_tamper_stale_future_and_duplicate_capture_validation():
    d=enriched();d['earnings_calendars'][0]['payload']['events']=[]
    with pytest.raises(ValueError,match='checksum'):calendar_source(d,'MSFT',now=NOW)
    d=enriched();assert calendar_source(d,'MSFT',now=NOW+timedelta(minutes=16)) is None
    with pytest.raises(ValueError,match='future'):calendar_source(d,'MSFT',now=NOW-timedelta(seconds=1))
    d['earnings_calendars']*=2
    with pytest.raises(ValueError,match='identity'):calendar_source(d,'MSFT',now=NOW)


def test_response_bound_and_duplicate_rows():
    d=response();d['earningsCalendar']*=21
    assert fetch(Session(d)).status=='error'
    d=response();d['earningsCalendar']*=2
    r=fetch(Session(d));assert len(r.events)==1 and r.status=='partial'


def test_momentum_stock_package_receives_calendar_without_clearing_risk_gates():
    from test_candidate_packages import stock_capture, NOW as STOCK_NOW
    from market_radar_ai.agents.candidate_packages import build_packages
    data={'earningsCalendar':[{'symbol':'AMD','date':STOCK_NOW.date().isoformat(),'hour':'bmo'}]}
    c=fetch_calendar('AMD',session=Session(data),env={'FINNHUB_API_KEY':'private-test'},clock=lambda:STOCK_NOW)
    d=enrich(stock_capture(),fetch=lambda _:c)
    r=build_packages(d,None,now=STOCK_NOW)['packages'][0]
    p=r['package'];assert len(p['calendar_source_ids'])==1
    assert 'broker_account_eligibility_unverified' in p['missing_evidence'] and p['plan'] is None
    assert reproduce(r,d,None,now=STOCK_NOW)['symbol']=='AMD'


def test_market_calendar_serves_80_symbols_with_one_request():
    from market_radar_ai.evidence.earnings_calendar import fetch_calendars
    symbols=['MSFT','AAPL']+['S'+chr(65+i//26)+chr(65+i%26) for i in range(78)]
    data=response()
    data['earningsCalendar'].append({'symbol':'AAPL','date':NOW.date().isoformat(),'hour':'bmo'})
    data['earningsCalendar'].append({'symbol':'OTHER','date':NOW.date().isoformat(),'hour':'amc'})
    session=Session(data)
    records=fetch_calendars(symbols,session=session,env={'FINNHUB_API_KEY':'private-test'},clock=lambda:NOW)
    assert len(session.calls)==1 and 'symbol' not in session.calls[0][1]['params']
    assert len(records)==80 and [r.symbol for r in records]==symbols
    assert records[0].events[0].symbol=='MSFT' and records[1].events[0].symbol=='AAPL'
    assert all(r.status=='empty' and not r.coverage_complete for r in records[2:])
    assert len({r.raw_payload_sha256 for r in records})==1
    assert all(r.retrieved_at==NOW and not r.trade_authorized for r in records)


@pytest.mark.parametrize('status,body',[(429,None),(403,None),(200,b'{}'),
    (200,b'x'*4_000_001),(200,b'{"earningsCalendar":[{}]}')])
def test_market_calendar_failure_never_becomes_empty_success(status,body):
    from market_radar_ai.evidence.earnings_calendar import fetch_calendars
    s=Session(status=status,body=body)
    rows=fetch_calendars(['MSFT','AAPL'],session=s,env={'FINNHUB_API_KEY':'private-test'},clock=lambda:NOW)
    assert len(s.calls)==1 and all(r.status=='error' and not r.events for r in rows)


def test_market_calendar_isolates_malformed_symbol_records():
    from market_radar_ai.evidence.earnings_calendar import fetch_calendars
    data=response();data['earningsCalendar'].append({'symbol':'AAPL','date':'invalid'})
    rows=fetch_calendars(['MSFT','AAPL'],session=Session(data),env={'FINNHUB_API_KEY':'private-test'},clock=lambda:NOW)
    assert rows[0].status=='received' and rows[1].status=='partial'
