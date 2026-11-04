from copy import deepcopy
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import pytest

from market_radar_ai.agents.scheduled_review import permitted, claim_review, decision_summary, execute, WORKFLOW_REF
from market_radar_ai.agents.github_budget import initial_state
from test_candidate_delivery import bundle

NOW = datetime(2026, 11, 4, 15, tzinfo=timezone.utc)
ENV = dict(GITHUB_REPOSITORY='Chiizzie/market-radar-ai', GITHUB_REF='refs/heads/main',
           GITHUB_WORKFLOW_REF=WORKFLOW_REF, GITHUB_EVENT_NAME='workflow_dispatch',
           GITHUB_RUN_ATTEMPT='1', SCHEDULED_REVIEW_MODE='paid')

class Store:
    def __init__(self): self.state=initial_state(); self.version=0
    def load(self): return deepcopy(self.state), str(self.version)
    def save(self, state, sha):
        assert sha == str(self.version)
        self.state=deepcopy(state); self.version+=1

@pytest.mark.parametrize('key,value', [('GITHUB_REF','refs/heads/other'),
    ('GITHUB_REPOSITORY','Chiizzie/market-radar'), ('GITHUB_WORKFLOW_REF','other'),
    ('GITHUB_RUN_ATTEMPT','2'), ('GITHUB_EVENT_NAME','push'),
    ('SCANNER_VERIFY_OUTSIDE_WINDOW','true'),('SCHEDULED_REVIEW_MODE','dry_run')])
def test_scope_rejects_wrong_identity(key,value):
    assert not permitted({**ENV,key:value}, NOW)

@pytest.mark.parametrize('date,allowed', [('2026-11-04T07:59:59+00:00',False),
    ('2026-11-04T08:00:00+00:00',True), ('2026-11-04T21:59:59+00:00',True),
    ('2026-11-04T22:00:00+00:00',False), ('2026-11-07T15:00:00+00:00',False),
    ('2026-11-08T15:00:00+00:00',False), ('2026-07-06T07:00:00+00:00',True),
    ('2026-07-06T21:00:00+00:00',False)])
def test_weekday_cutoff_and_dst(date,allowed):
    assert permitted(ENV,datetime.fromisoformat(date)) is allowed

def test_durable_market_daily_quota_and_new_day():
    s=Store()
    assert claim_review(s,'stocks',NOW)
    assert not claim_review(s,'stocks',NOW)
    assert claim_review(s,'crypto',NOW)
    assert claim_review(s,'stocks',NOW+timedelta(days=1))
    assert all(e['actual']==0 for e in s.state['entries'].values())

def test_lost_marker_reply_blocks_generation_and_retry():
    class Lost(Store):
        def save(self,state,sha):
            super().save(state,sha)
            raise RuntimeError('lost response')
    s=Lost()
    with pytest.raises(RuntimeError): claim_review(s,'stocks',NOW)
    assert not claim_review(s,'stocks',NOW)
    assert next(iter(s.state['entries'].values()))['actual'] is None

def test_budget_headroom_defers_without_reset():
    s=Store(); s.state['entries']['old']={'day':'2026-11-03','reserved':4900000,'actual':4900000,'usage':None}
    assert not claim_review(s,'stocks',NOW)
    assert s.version==0

def test_unknown_budget_charge_counts_as_spent():
    s=Store(); s.state['entries']['unknown']={'day':'2026-11-04','reserved':400000,'actual':None,'usage':None}
    assert not claim_review(s,'crypto',NOW)

def test_offscope_no_network_or_models(tmp_path,monkeypatch):
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.build_packages',lambda *a,**k:pytest.fail('network preparation'))
    r=execute({},None,tmp_path/'run',env={},clock=lambda:NOW)
    assert r['model_calls']==0 and r['state']=='outside_review_scope_or_window'

@pytest.mark.parametrize('stale',[False,True])
def test_reproduced_decision_retains_gaps_and_no_trade(stale):
    d=decision_summary(*bundle(stale))
    assert d['final_decision']=='NO_ACTION' and not d['trade_authorized']
    assert d['model_calls']==8 and d['plan'] is None
    assert 'six_agent_review_not_run' not in d['blockers']
    assert 'broker_account_eligibility_unverified' in d['blockers']
    assert ('review_evidence_expired' in d['blockers']) is stale

def test_incomplete_review_cannot_become_decision():
    args=bundle(); args[-1]['calls'].pop()
    with pytest.raises(ValueError): decision_summary(*args)

def test_scheduled_delivery_accepts_only_exact_workflow():
    import hashlib
    from market_radar_ai.dashboard.candidate_delivery import deliver
    class Session:
        def post(self,url,**kw):
            return type('Response',(),{'status_code':200,'json':lambda self:{'ok':True,'archive_id':hashlib.sha256(kw['data']).hexdigest()}})()
    r=deliver(*bundle(),env={**ENV,'SEND_CANDIDATE_REVIEW':'true','REVIEW_INGEST_SECRET':'x'*32},clock=lambda:NOW,session=Session())
    assert r['state']=='candidate_archive_delivery_confirmed'
    with pytest.raises(ValueError):
        deliver(*bundle(),env={**ENV,'GITHUB_WORKFLOW_REF':'bad','SEND_CANDIDATE_REVIEW':'true'},clock=lambda:NOW,session=Session())

def test_cycle_delivers_once_then_skips_without_more_models(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from test_candidate_review import NOW as FIXTURE_NOW
    record,capture,feed,audit=bundle()
    s=Store(); calls=[]
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.GitHubBudgetStore',lambda _:s)
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.OpenAIPilot',lambda **k:object())
    fx=SimpleNamespace(eur_per_unit='0.9',model_dump=lambda **k:{'eur_per_unit':'0.9'})
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.YahooFxProvider',lambda:SimpleNamespace(fetch=lambda *a,**k:fx))
    def paid(client, record, capture, feed, **kwargs):
        from market_radar_ai.agents.candidate_review import run
        from test_candidate_review import answer
        calls.append('eight')
        result=run(record,capture,feed,answer,clock=kwargs['clock'])
        return {**audit,'result':result,'calls':[{'stage':r['stage'],'state':'received',
                'estimated_cost_microeur':123,'untrusted_response':r} for r in result['reviews']]}
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.run_paid',paid)
    monkeypatch.setattr('market_radar_ai.agents.scheduled_review.deliver',lambda *a,**k:{'state':'candidate_archive_delivery_confirmed'})
    # Fixture is a weekday within the authorized clock window.
    env={**ENV,'OPENAI_API_KEY':'test','GH_BUDGET_TOKEN':'test'}
    result=execute(capture,feed,tmp_path/'one',env=env,clock=lambda:FIXTURE_NOW)
    assert result['state']=='decision_completed' and result['model_calls']==8
    result=execute(capture,feed,tmp_path/'two',env=env,clock=lambda:FIXTURE_NOW)
    assert result['state']=='daily_review_quota_reached' and result['model_calls']==0
    assert calls==['eight']


def test_explicit_recovery_is_date_scope_and_package_bound():
    from market_radar_ai.agents.scheduled_review import authorized_recovery_bucket
    record={'package': {'schema_version':'session-evidence-package-v1', 'review_slot':'intraday'}}
    env={**ENV,'SCHEDULED_RECOVERY_DATE':'2026-11-04'}
    assert authorized_recovery_bucket(record,env,NOW)=='stocks_verified_recovery'
    assert authorized_recovery_bucket(record,ENV,NOW)=='stocks_intraday'
    assert authorized_recovery_bucket(record,env,NOW+timedelta(days=1))=='stocks_intraday'
    assert authorized_recovery_bucket(record,{**env,'GITHUB_RUN_ATTEMPT':'2'},NOW)=='stocks_intraday'


def test_paid_failure_recovery_preserves_charges_and_only_claims_once():
    s=Store()
    s.state['entries']['previous-paid-call']={'day':'2026-11-04','reserved':100000,'actual':98000,'usage':None}
    assert claim_review(s,'stocks_intraday',NOW)
    original=deepcopy(s.state['entries'])
    assert claim_review(s,'stocks_verified_recovery',NOW)
    assert not claim_review(s,'stocks_verified_recovery',NOW)
    assert all(s.state['entries'][k]==v for k,v in original.items())


def test_recovery_cannot_bypass_spending_limit():
    s=Store()
    s.state['entries']['previous-paid-call']={'day':'2026-11-04','reserved':400000,'actual':400000,'usage':None}
    assert not claim_review(s,'stocks_verified_recovery',NOW)
    assert s.version==0


def test_reference_verification_requires_dated_checks_and_cannot_repeat():
    from market_radar_ai.agents.scheduled_review import authorized_recovery_bucket
    r={'package':{'schema_version':'session-evidence-package-v1','review_slot':'intraday'}}
    env={**ENV,'REFERENCE_VERIFICATION_DATE':'2026-11-04','ENABLE_STOCK_CHECKS':'true'}
    assert authorized_recovery_bucket(r,env,NOW)=='stocks_reference_verification'
    assert authorized_recovery_bucket(r,env,NOW+timedelta(days=1))=='stocks_intraday'
    assert authorized_recovery_bucket(r,{**env,'ENABLE_STOCK_CHECKS':'false'},NOW)=='stocks_intraday'
    s=Store()
    assert claim_review(s,'stocks_verified_recovery',NOW)
    assert claim_review(s,'stocks_reference_verification',NOW)
    assert not claim_review(s,'stocks_reference_verification',NOW)
