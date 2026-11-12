"""Regressions from 11–12 November operational evidence. No network calls."""
import json
import sys
from datetime import timedelta
from types import SimpleNamespace

import pytest
import requests

from market_radar_ai.dashboard.account_sync import Reader, public_error
from market_radar_ai.dashboard.run_diagnostics import build_report
from market_radar_ai.market_data import stock_checks
from test_catalogue_reuse import record
from test_stock_checks import NOW, payload
from market_radar_ai.market_data.admission import FxQuote


def test_stock_cli_reuses_collector_catalogue_but_fetches_fresh_market_evidence(tmp_path,monkeypatch):
    original=record(); later=NOW+timedelta(seconds=60)
    source=tmp_path/'capture.json'; target=tmp_path/'fresh.json'
    source.write_text(json.dumps({'captures':[{'market':'stocks','requested_symbol':'IBM'}],
                                 'stock_reference_checks':original}))
    class NoCatalogue:
        def fetch(self):raise AssertionError('duplicate broker metadata request')
    calls=[]
    def get(url,params,env,session):
        calls.append(url)
        if url.endswith('/clock'):return {**payload()['market_clock'],'timestamp':later.isoformat()}
        return {'quotes':{'IBM':{**payload()['quotes']['quotes']['IBM'],'t':later.isoformat()}}}
    real=stock_checks.collect
    def collect(symbols,**kw):
        return real(symbols,**kw,clock=lambda:later,catalogue=NoCatalogue(),
            fx_provider=SimpleNamespace(fetch=lambda *a,**k:FxQuote(native_currency='USD',
                eur_per_unit='.9',source='fixture',observed_at=later)))
    monkeypatch.setattr(stock_checks,'collect',collect);monkeypatch.setattr(stock_checks,'get',get)
    monkeypatch.setattr(sys,'argv',['checks','--capture',str(source),'--output',str(target)])
    stock_checks.main(); fresh=json.loads(target.read_text())['stock_reference_checks']
    assert len(calls)==2
    assert fresh['payload']['catalogue_observed_at']==NOW.isoformat()
    assert fresh['payload']['retrieved_at']==later.isoformat()
    assert stock_checks.evaluate(fresh,now=later)['stocks'][0]['quote_status']=='current_reference_only'
    assert json.loads(source.read_text())['stock_reference_checks']==original


def test_wide_universe_manifest_still_explains_known_symbols(tmp_path):
    # Observed production file was 4,625,840 bytes, beyond the generic 4 MB cap.
    manifest={'symbols':[{'symbol':'NVDA','snapshot_status':'fresh','day_change_pct':3,
        'detail_selected':True,'selection_reason':'selected_for_research'}],
        'note':'x'*4_625_840}
    (tmp_path/'discovery-selection.json').write_text(json.dumps(manifest))
    (tmp_path/'qualification.json').write_text(json.dumps({'candidates':[{
        'candidate_id':'stocks:NVDA','paper_blockers':['relative_volume_below_1_5']}]}))
    (tmp_path/'discovery.json').write_text(json.dumps({'catalyst_links':{'rows':[{
        'symbol':'NVDA','catalogue_member':True}]}}))
    report=build_report(tmp_path,now=NOW)
    assert report['unreadable_artifacts']==[]
    assert report['missed_moves']['rows'][0]['symbol']=='NVDA'
    assert report['missed_moves']['rows'][0]['detail_selected'] is True
    assert report['catalyst_links']['rows'][0]['selection_reason']=='selected_for_research'


def test_missing_manifest_is_unknown_not_outside_catalogue(tmp_path):
    (tmp_path/'discovery.json').write_text(json.dumps({'catalyst_links':{'rows':[{
        'symbol':'AMD','catalogue_member':True}]}}))
    report=build_report(tmp_path,now=NOW)
    assert report['missed_moves']['selection_evidence_status']=='unavailable'
    assert report['catalyst_links']['rows'][0]['detail_selected'] is None
    assert report['catalyst_links']['rows'][0]['selection_reason']=='selection_evidence_unavailable'


def test_large_manifest_bound_does_not_relax_other_artifact_bounds(tmp_path):
    (tmp_path/'status.json').write_text(json.dumps({'state':'x'*4_000_001}))
    report=build_report(tmp_path,now=NOW)
    assert report['unreadable_artifacts']==['status.json']


class Reply:
    def __init__(self,status=200,body=b'[]',headers=None):
        self.status_code,self.body,self.headers=status,body,headers or {}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,*args):yield self.body


class Session:
    def __init__(self,answers):self.answers=iter(answers);self.calls=[]
    def get(self,url,**kw):
        self.calls.append((url,kw));r=next(self.answers)
        if isinstance(r,Exception):raise r
        return r


@pytest.mark.parametrize('first',[requests.Timeout('SECRET'),requests.ConnectionError('SECRET'),
    Reply(503),Reply(429,headers={'x-ratelimit-reset':'1007'})])
def test_transient_account_get_can_recover_without_posts(first):
    session=Session([first,Reply()]);waits=[]
    reader=Reader('key','secret',session=session,sleep=waits.append,clock=lambda:1000)
    assert reader('/api/v0/equity/positions')==[]
    assert len(session.calls)==2 and reader.retries==1 and 5<=waits[0]<=10
    assert all(k['allow_redirects'] is False for _,k in session.calls)


@pytest.mark.parametrize('status',[301,401,403,404])
def test_nontransient_account_error_is_not_retried(status):
    session=Session([Reply(status)]);reader=Reader('key','secret',session=session,sleep=lambda _:None)
    with pytest.raises(RuntimeError,match='account_read_http_'+str(status)):
        reader('/api/v0/equity/positions')
    assert len(session.calls)==1


@pytest.mark.parametrize('header,value',[('x-ratelimit-reset','1020'),('Retry-After','NaN'),
    ('Retry-After','Infinity'),('Retry-After','bad')])
def test_long_or_invalid_backoff_is_not_ignored(header,value):
    session=Session([Reply(429,headers={header:value})]);waits=[]
    reader=Reader('key','secret',session=session,sleep=waits.append,clock=lambda:1000)
    with pytest.raises(RuntimeError,match='account_read_backoff_'):
        reader('/api/v0/equity/positions')
    assert len(session.calls)==1 and waits==[]


def test_account_retry_budget_is_shared_and_persistent_failure_visible():
    session=Session([Reply(503),Reply(),Reply(503),Reply(),Reply(503)])
    reader=Reader('key','secret',session=session,sleep=lambda _:None)
    for _ in range(2):assert reader('/api/v0/equity/positions')==[]
    with pytest.raises(RuntimeError,match='account_read_http_503'):
        reader('/api/v0/equity/positions')
    assert reader.retries==2 and len(session.calls)==5


def test_account_failures_are_sanitized_and_invalid_body_not_retried():
    session=Session([Reply(body=b'not json SECRET')])
    reader=Reader('key','secret',session=session,sleep=lambda _:None)
    with pytest.raises(RuntimeError,match='account_read_invalid_json'):
        reader('/api/v0/equity/positions')
    assert len(session.calls)==1
    assert public_error(RuntimeError('SECRET account balance https://example.com'))=='account_sync_failed'
    assert public_error(RuntimeError('account_read_http_503 SECRET'))=='account_sync_failed'
    assert public_error(RuntimeError('account_read_transport_error'))=='account_read_transport_error'


def test_main_failure_identifies_stage_without_private_exception(monkeypatch,capsys):
    from market_radar_ai.dashboard import account_sync
    monkeypatch.setenv('ENABLE_ACCOUNT_SYNC','true')
    for k in ['TRADING212_API_KEY','TRADING212_API_SECRET','REVIEW_INGEST_SECRET']:monkeypatch.setenv(k,'x'*32)
    monkeypatch.setattr('market_radar_ai.dashboard.collection_schedule.scheduled_scope',lambda *a:True)
    reader=Reader('k','s',session=Session([requests.Timeout('PRIVATE'),requests.Timeout('PRIVATE')]),sleep=lambda _:None)
    monkeypatch.setattr(account_sync,'Reader',lambda *a:reader)
    with pytest.raises(SystemExit):account_sync.main()
    result=json.loads(capsys.readouterr().out)
    assert result=={'status':'account_sync_failed','stage':'account_summary',
                    'code':'account_read_transport_error','read_retries':1}
