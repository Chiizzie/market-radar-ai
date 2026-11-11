import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from market_radar_ai.dashboard.execution_readiness import build
from market_radar_ai.agents.github_budget import initial_state

NOW = datetime(2026,11,8,21,tzinfo=UTC)
ENV = {'AI_KEY_PRESENT':'true','WATCHER_ENABLED':'true','ALPACA_API_KEY':'offline-key','ALPACA_API_SECRET':'offline-secret'}


class Budget:
    def __init__(self, state=None): self.state = state or initial_state()
    def load(self): return self.state, 'a'*40


class Client:
    def read(self, experiment, day, after): return {'events':[], 'next':after}


class Response:
    def __init__(self, data, status=200): self.data=data;self.status_code=status
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def iter_content(self,n): yield json.dumps(self.data).encode()


class Session:
    def __init__(self, now=NOW, opened=False, quote_age=100000, clock_age=0, status=200):
        self.now=now;self.opened=opened;self.quote_age=quote_age;self.clock_age=clock_age;self.status=status;self.urls=[]
    def get(self,url,**kwargs):
        self.urls.append(url)
        if url.endswith('/clock'):
            raw={'is_open':self.opened,'timestamp':(self.now-timedelta(seconds=self.clock_age)).isoformat(),
                 'next_open':(self.now+timedelta(days=1)).isoformat(),'next_close':(self.now+timedelta(days=1,hours=6)).isoformat()}
        else: raw={'quote':{'bp':100,'ap':100.01,'t':(self.now-timedelta(seconds=self.quote_age)).isoformat()}}
        return Response(raw,self.status)


class GitHub:
    def __init__(self,now=NOW,conclusion='success'):self.now=now;self.conclusion=conclusion
    def get(self,path):
        if 'workflows' in path:
            return {'workflow_runs':[{'id':123,'head_branch':'main','name':'Scheduled research collection',
                'status':'completed','conclusion':self.conclusion,'created_at':self.now.isoformat(),
                'run_started_at':self.now.isoformat(),'updated_at':self.now.isoformat()}]}
        names=['collect','review','paper-watcher','method-shadow','account-sync','market-context']
        return {'total_count':6,'jobs':[{'name':n,'status':'completed','conclusion':self.conclusion,
            'started_at':self.now.isoformat(),'completed_at':self.now.isoformat()} for n in names]}


def result(**kwargs):
    return build(now=kwargs.pop('now',NOW),env=kwargs.pop('env',ENV),client=Client(),
        session=kwargs.pop('session',Session()),budget_store=kwargs.pop('budget_store',Budget()),
        github=kwargs.pop('github',GitHub()),**kwargs)


def states(r): return {c['id']:c['status'] for c in r['checks']}


def test_weekend_is_paused_and_empty_observation_is_not_success():
    r=result();s=states(r)
    assert s['weekday_window']==s['reference_quote_probe']==s['scanner_dispatch']=='paused'
    assert s['observer_under_load']==s['comparison_recovery']==s['method_recovery']=='pending'
    assert r['status']=='awaiting_live_evidence' and r['model_calls']==0 and not r['trade_authorized']
    assert 'offline-secret' not in json.dumps(r) and 'offline-key' not in json.dumps(r)


def test_open_session_stale_quote_and_failed_jobs_are_attention():
    now=datetime(2026,11,9,15,tzinfo=UTC)
    r=result(now=now,session=Session(now,True,120),github=GitHub(now,'failure'))
    assert states(r)['reference_quote_probe']=='unavailable'
    assert states(r)['scanner_jobs']=='blocked' and r['status']=='attention_required'


def test_budget_headroom_accounts_for_lifetime_unsettled_reservations():
    state=initial_state();state['entries']['offline-reservation']={'day':'2026-10-01','reserved':state['limits_microeur']['lifetime']-100000,'actual':None,'usage':None}
    r=result(budget_store=Budget(state))
    assert states(r)['ai_spending_headroom']=='blocked'
    assert r['budget']['periods']['lifetime']['remaining_microeur']==100000


def test_disabled_observer_missing_key_and_outage_never_turn_green():
    r=result(env={**ENV,'AI_KEY_PRESENT':'false','WATCHER_ENABLED':'false'},session=Session(status=403))
    s=states(r)
    assert s['ai_key_configuration']==s['paper_observer_configuration']=='blocked'
    assert s['market_calendar']==s['reference_quote_probe']=='unavailable'
    assert r['market_clock'] is None


def test_future_clock_and_future_quote_are_unavailable():
    r=result(session=Session(clock_age=-3600,quote_age=-1000))
    assert states(r)['market_calendar']==states(r)['reference_quote_probe']=='unavailable'


def test_no_stale_or_empty_load_claim():
    now=datetime(2026,11,9,15,tzinfo=UTC)
    raw={'as_of':now.isoformat(),'cohort_count':1,'observation_health':{'quotes_received':8,'error_polls':0,'maximum_poll_gap_seconds':5}}
    event={'kind':'report','occurred_at':now.isoformat(),'payload_json':json.dumps(raw)}
    r=result(now=now,session=Session(now,True,1),github=GitHub(now),source_events=[event])
    assert states(r)['observer_under_load']=='pass'
    raw['observation_health']['maximum_poll_gap_seconds']=18
    event['payload_json']=json.dumps(raw)
    assert states(result(now=now,source_events=[event]))['observer_under_load']=='pending'


def test_due_backups_and_expired_cost_schedule_are_explicit():
    now=datetime(2026,12,8,23,tzinfo=UTC)
    r=result(now=now,session=Session(now),github=GitHub(now))
    assert states(r)['comparison_recovery']==states(r)['method_recovery']=='unavailable'
    assert states(r)['cost_schedule']=='blocked'


def test_quote_arriving_after_started_at_is_checked_at_receipt():
    now=datetime(2026,11,9,15,tzinfo=UTC)
    r=result(now=now,session=Session(now,True,-2),github=GitHub(now),
             receipt_clock=lambda:now+timedelta(seconds=3))
    assert states(r)['reference_quote_probe']=='pass'
    assert '1.0 seconds' in next(c['detail'] for c in r['checks'] if c['id']=='reference_quote_probe')
    future=result(now=now,session=Session(now,True,-40),github=GitHub(now),receipt_clock=lambda:now+timedelta(seconds=3))
    assert states(future)['reference_quote_probe']=='unavailable'
    stale=result(now=now,session=Session(now,True,89),github=GitHub(now),receipt_clock=lambda:now+timedelta(seconds=3))
    assert states(stale)['reference_quote_probe']=='unavailable'
