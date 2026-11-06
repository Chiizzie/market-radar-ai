from copy import deepcopy


def test_symbol_context_gap_does_not_fail_healthy_peers_but_outage_does():
    from market_radar_ai.market_data.stock_context import connectivity_exit_code
    def row(daily, intraday):
        return {'payload': {'daily': {'status': daily}, 'intraday': {'status': intraday}}}
    missing = row('unavailable', 'unavailable')
    good = row('received', 'received')
    assert connectivity_exit_code({'stock_context': [missing, good]}) == 0
    assert connectivity_exit_code({'stock_context': [missing, missing]}) == 1
    assert connectivity_exit_code({'stock_context': []}) == 0
from datetime import datetime, timedelta, timezone
import json
import pytest

from market_radar_ai.market_data.stock_context import fetch_context, enrich
from market_radar_ai.agents.context_packages import build_context_packages
from market_radar_ai.agents.candidate_packages import canonical, digest
from market_radar_ai.agents.candidate_review import run, reproduce
from market_radar_ai.agents.github_candidate_review import execute
from market_radar_ai.evidence.scanner_feed import collect
from test_candidate_review import answer, ENV

NOW=datetime(2026,11,4,13,0,tzinfo=timezone.utc)


class Session:
    def __init__(self, mutation=None): self.mutation=mutation;self.calls=[]
    def get(self,url,**kw):
        self.calls.append((url,kw))
        assert url=='https://data.alpaca.markets/v2/stocks/MSFT/bars'
        assert kw['allow_redirects'] is False and kw['params']['feed']=='iex'
        assert kw['params']['currency']=='USD' and kw['params']['limit']==1000
        frame=kw['params']['timeframe']
        times=[NOW.replace(hour=5)-timedelta(days=i) for i in (3,2,1,0)] if frame=='1Day' else [NOW-timedelta(minutes=5),NOW]
        data={'symbol':'MSFT','bars':[{'t':t.isoformat(),'o':100,'h':102,'l':99,'c':101,'v':100} for t in times], 'next_page_token':None}
        if self.mutation:self.mutation(frame,data)
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def iter_content(self,*a):yield json.dumps(data).encode()
        return Response()


def context(now=NOW,mutation=None):
    return fetch_context('MSFT',session=Session(mutation),
        env={'ALPACA_API_KEY':'private-key','ALPACA_API_SECRET':'private-secret'},clock=lambda:now)


def document(record=None):
    return {'captures':[{'market':'stocks','requested_symbol':'MSFT'}],
        'stock_context':[context() if record is None else record]}


def test_prior_days_and_one_premarket_bar_make_six_role_package():
    d=document();p=d['stock_context'][0]['payload']
    assert len(p['daily']['bars'])==3 and len(p['intraday']['bars'])==1
    b=build_context_packages(d,None,now=NOW)['packages'][0]['package']
    assert b['research_mode']=='PREMARKET_CONTEXT' and len(b['roles'])==6
    assert b['native_currency']=='USD' and b['eur_conversion']=='not_supplied'
    assert b['plan'] is None and not b['trade_authorized']
    assert 'context_is_not_trade_admission' in b['missing_evidence']


def test_prior_history_alone_can_be_reviewed_before_any_current_bar():
    def no_bars(frame,data):
        if frame=='5Min':data['bars']=[]
    d=document(context(mutation=no_bars))
    b=build_context_packages(d,None,now=NOW)['packages'][0]['package']
    assert 'current_session_bars_missing' in b['missing_evidence']
    assert b['research_mode']=='PREMARKET_CONTEXT'


def test_six_independent_roles_then_debate_then_conclusion_on_context():
    d=document();record=build_context_packages(d,None,now=NOW)['packages'][0]
    stages=[]
    def ask(stage,payload,schema):
        assert payload['evidence_status']=='CURRENT_CONTEXT_ONLY'
        assert [p['stage'] for p in payload['peer_reviews']]==(stages if stage in ('debate','conclusion') else [])
        stages.append(stage)
        return answer(stage,payload,schema)
    result=run(record,d,None,ask,clock=lambda:NOW)
    assert len(stages)==8 and result['schema_version']=='context-review-result-v1'
    assert result['evidence_status']=='CURRENT_CONTEXT_ONLY' and result['plan'] is None
    assert reproduce(json.loads(json.dumps(record)),json.loads(json.dumps(d)),None,now=NOW)['symbol']=='MSFT'


def test_context_dry_run_requires_no_twenty_bar_shortlist(tmp_path):
    status=execute(document(),None,tmp_path/'context',env={**ENV,'REVIEW_SCOPE':'context','CANDIDATE_MARKET':'stocks'},clock=lambda:NOW)
    assert status['state']=='ready_dry_run' and status['model_calls']==0
    assert status['research_scope']=='context'
    assert not (tmp_path/'context/dashboard-archive.json').exists()


@pytest.mark.parametrize('extra',[{'CANDIDATE_MARKET':'crypto'},{'SEND_CANDIDATE_REVIEW':'true'}])
def test_context_never_silently_enters_wrong_market_or_archive(tmp_path,extra):
    with pytest.raises(ValueError):execute(document(),None,tmp_path/'out',env={**ENV,'REVIEW_SCOPE':'context',**extra},clock=lambda:NOW)
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('fault',['symbol','pagination','future','duplicate','nan'])
def test_invalid_source_is_unavailable_without_leaking(fault):
    def mutate(frame,data):
        if fault=='symbol':data['symbol']='OTHER'
        if fault=='pagination':data['next_page_token']='private-secret'
        if fault=='future':data['bars'][-1]['t']=(NOW+timedelta(days=1)).isoformat()
        if fault=='duplicate':data['bars'].append(deepcopy(data['bars'][0]))
        if fault=='nan':data['bars'][0]['c']='NaN'
    r=context(mutation=mutate)
    assert r['payload']['status']=='partial'
    assert 'private' not in canonical(r)
    assert not build_context_packages(document(r),None,now=NOW)['packages']


def test_context_checksum_and_fresh_retrieval_required():
    d=document();d['stock_context'][0]['payload']['symbol']='OTHER'
    with pytest.raises(ValueError,match='checksum'):build_context_packages(d,None,now=NOW)
    assert not build_context_packages(document(),None,now=NOW+timedelta(seconds=901))['packages']


def test_no_records_if_every_source_is_missing():
    r=fetch_context('MSFT',session=object(),env={},clock=lambda:NOW)
    assert not build_context_packages(document(r),None,now=NOW)['packages']


def test_unverified_macro_is_not_asset_linked_or_trade_evidence():
    feed={'status':'ok','scope':'MACRO','retrieved_at':NOW.isoformat(),'items':[
        {'title':'Policy announcement.','url':'https://www.federalreserve.gov/test',
         'source':'Federal Reserve Board','symbols':[],'kind':'news',
         'published_at':(NOW-timedelta(hours=2)).isoformat(),'retrieved_at':NOW.isoformat()}]}
    b=build_context_packages(document(),feed,now=NOW)['packages'][0]['package']
    assert len(b['macro_source_ids'])==1 and not b['news_source_ids']
    assert b['context_only_news_ids']==b['macro_source_ids']
    assert 'symbol_linked_news_missing' in b['missing_evidence']


def test_early_opening_afterhours_and_weekend_phases_have_no_twenty_bar_gate():
    for when,phase in [(NOW.replace(hour=14,minute=35),'OPENING_CONTEXT'),
                       (NOW.replace(hour=18),'INTRADAY_CONTEXT'),
                       (NOW.replace(hour=22),'AFTER_HOURS_CONTEXT'),
                       (NOW+timedelta(days=3),'WEEKEND_CONTEXT')]:
        # Reuse explicitly historical daily evidence; update only capture receipt in this synthetic fixture.
        d=document();p=d['stock_context'][0]['payload'];p['retrieved_at']=when.isoformat()
        for k in ('daily','intraday'):p[k]['request_end']=when.isoformat()
        if phase=='WEEKEND_CONTEXT':p['intraday'].update(status='empty',bars=[])
        d['stock_context'][0]['payload_sha256']=digest(p)
        b=build_context_packages(d,None,now=when)['packages'][0]['package']
        assert b['research_mode']==phase and not b['trade_authorized']
        if phase=='AFTER_HOURS_CONTEXT':assert 'entry_cutoff_reached' in b['missing_evidence']


def test_context_review_expiry_is_not_extended():
    d=document();record=build_context_packages(d,None,now=NOW)['packages'][0]
    with pytest.raises(ValueError,match='expired'):run(record,d,None,answer,clock=lambda:NOW+timedelta(minutes=5))


def test_requested_company_news_queries_cover_all_eight_without_inventing_links():
    seen=[]
    def fetch(symbol):
        seen.append(symbol)
        return {'status':'ok','scope':'LEADS','retrieved_at':NOW.isoformat(),'items':[]}
    collect(company_symbols=['NVDA','MSFT','AAPL','AMD','META','AMZN','GOOGL','TSLA'],
        company_fetch=fetch,public_fetch=lambda **kw:{'status':'error','items':[]},clock=lambda:NOW)
    assert len(seen)==8 and 'AMD' in seen
    with pytest.raises(ValueError):collect(company_symbols=['../orders'])
    from market_radar_ai.evidence.combine import combine_feeds
    with pytest.raises(ValueError):combine_feeds([{'status':'error','items':[]}]*45,now=NOW)


def test_context_paid_adapter_keeps_audit_and_does_not_use_trade_archive(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import market_radar_ai.agents.github_candidate_review as runner
    import market_radar_ai.agents.openai_pilot as pilot
    import market_radar_ai.agents.github_budget as budget
    import market_radar_ai.dashboard.candidate_delivery as delivery
    from market_radar_ai.market_data.admission import FxQuote
    stages=[]
    class Ledger:
        def __init__(self,store):pass
        def summary(self):return {'test_only':True,'calls':len(stages)}
    class Client:
        def __init__(self,**kw):self.ledger=kw['ledger']
        def call(self,**kw):
            p=json.loads(kw['prompt']);stages.append(p['stage'])
            assert kw['request_id'].startswith('context-review-v1:')
            return SimpleNamespace(data=answer(p['stage'],p,kw['schema']),response_id='test',cost_usd='0.001',
                estimated_cost_microeur=900,input_tokens=1000,output_tokens=100,counted_input_tokens=1000)
    class FX:
        def fetch(self,*args,**kw):return FxQuote(native_currency='USD',eur_per_unit='0.9',observed_at=NOW,source='test')
    monkeypatch.setattr(runner,'GitHubBudgetStore',lambda token:object())
    for module in (runner,budget):monkeypatch.setattr(module,'GitHubSpendingLedger',Ledger)
    for module in (runner,pilot):monkeypatch.setattr(module,'OpenAIPilot',Client)
    monkeypatch.setattr(runner,'YahooFxProvider',FX)
    monkeypatch.setattr(delivery,'export_archive',lambda *a:pytest.fail('wrong archive'))
    status=execute(document(),None,tmp_path/'run',env={**ENV,'REVIEW_SCOPE':'context',
        'CANDIDATE_REVIEW_MODE':'paid','OPENAI_API_KEY':'test','GH_BUDGET_TOKEN':'test'},clock=lambda:NOW)
    audit=json.loads((tmp_path/'run/review.json').read_text())
    assert audit['schema_version']=='paid-context-review-v1' and audit['state']=='completed'
    assert status['model_calls']==8 and status['dashboard_delivery_state']=='context_archive_not_connected'
    assert not (tmp_path/'run/dashboard-archive.json').exists()
