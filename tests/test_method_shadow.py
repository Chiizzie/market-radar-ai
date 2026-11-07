"""Synthetic offline evidence only; no fixtures are written to production."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from types import SimpleNamespace
import json

import pytest

from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.method_scenarios import scenario, PROTOCOL_ID
from market_radar_ai.agents.method_shadow import MethodShadow
from market_radar_ai.agents.comparison_live import envelope
from market_radar_ai.agents.paper_outcomes import Quote, replay_long
from market_radar_ai.agents.paper_comparison import _plan
from market_radar_ai.market_data.anchored_vwap import measure
from test_comparison_live import MemoryEvents

NOW=datetime(2026,11,6,16,0,1,tzinfo=UTC)


def fixture():
    def bar(at,close,*,interval='5m',high=None,low=None,volume='10000'):
        return {'symbol':'TEST','interval':interval,'timestamp':at.isoformat(),'open':str(Decimal(str(close))-Decimal('.05')),
            'close':str(close),'high':str(high or Decimal(str(close))+Decimal('.1')),
            'low':str(low or Decimal(str(close))-Decimal('.15')),'volume':volume,'quote_currency':'USD','source':'alpaca_iex'}
    prices=['99','99.2','99.4','99.5','99.6','99.7','99.8','99.9','100','100.1','100.2','100.3','100.2','100.3','100.3','100.0','99.8','100.4']
    candles=[bar(NOW.replace(hour=14,minute=30,second=0)+timedelta(minutes=i*5),c,
                 high='105' if i==9 else None,low='99.65' if i>=15 else None,
                 volume='20000' if i>=15 else '10000') for i,c in enumerate(prices)]
    dates=['2026-10-29','2026-10-30','2026-11-02','2026-11-03','2026-11-04','2026-11-05']
    days=[bar(datetime.fromisoformat(d+'T14:00:00+00:00'),str(100+i),interval='1d',high='110') for i,d in enumerate(dates)]
    context={'schema_version':'stock-context-capture-v1','symbol':'TEST','provider':'alpaca_iex','native_currency':'USD',
        'trade_authorized':False,'status':'received','retrieved_at':NOW.isoformat(),
        'daily':{'status':'received','bars':days}}
    p={'schema_version':'stock-reference-checks-v1','trade_authorized':False,'symbols':['TEST'],'retrieved_at':NOW.isoformat(),
       'catalogue_candidates':{'TEST':[{'ticker':'TEST_US_EQ'}]},
       'market_clock':{'is_open':True,'timestamp':NOW.isoformat(),'next_open':'2026-11-09T14:30:00Z','next_close':'2026-11-06T21:00:00Z'},
       'fx':{'native_currency':'USD','eur_per_unit':'0.9','observed_at':NOW.isoformat(),'source':'test'},
       'quotes':{'currency':'USD','quotes':{'TEST':{'t':NOW.isoformat(),'bp':100.40,'ap':100.45,'bs':100,'as':100}}}}
    return {'symbol':'TEST','candles':candles,'daily':days,'context':context,'bars_received_at':NOW.isoformat(),
        'reference_checks':{'payload':p,'payload_sha256':digest(p)},
        'news_check':{'schema_version':'chart-news-check-v1','query_symbol':'TEST','status':'checked_bounded_source',
          'scope':'PUBLISHER_TAGGED_STOCK_NEWS_PARTIAL','checked_at':NOW.isoformat(),'validated_item_count':0,
          'coverage_complete':False,'fresh_catalyst_required':False}}


def test_real_detector_and_net_cost_plan():
    i=fixture(); s=scenario(i,now=NOW)
    assert s['blockers']==[]
    p=_plan(s['plan'])
    assert p.planned_loss<=20 and p.entry*p.quantity<=500
    assert (p.target-p.entry)*p.quantity-p.costs_eur >= p.planned_loss*Decimal('1.999999')
    assert s['features']['completed_15m_buckets']==6
    assert s['shadow_only'] and s['trade_authorized'] is False


@pytest.mark.parametrize('change,reason',[
    ('anchor','session_anchor_bar_missing'),('gap','session_bars_have_gaps_or_duplicates'),
    ('future','latest_completed_bar_missing_or_stale'),('daily','daily_context_stale_future_or_duplicated'),
    ('wrong_symbol','method_bar_identity_or_values_invalid'),('volume','reclaim_volume_insufficient'),
    ('daily_trend','daily_trend_not_confirmed'),('split','daily_discontinuity_requires_corporate_action_check')])
def test_missing_or_noncausal_data_never_reanchors(change,reason):
    i=fixture()
    if change=='anchor':
        for c in i['candles']: c['timestamp']=(datetime.fromisoformat(c['timestamp'])+timedelta(minutes=5)).isoformat()
    if change=='gap': i['candles'][8]['timestamp']=i['candles'][7]['timestamp']
    if change=='future': i['candles'].append({**i['candles'][-1],'timestamp':NOW.replace(second=0).isoformat()})
    if change=='daily': i['daily'][-1]['timestamp']=NOW.isoformat()
    if change=='wrong_symbol': i['candles'][0]['symbol']='OTHER'
    if change=='volume':
        for c in i['candles']: c['volume']='10000'
    if change=='daily_trend':
        for c in i['daily']: c.update(open='100',close='100',low='99')
    if change=='split': i['daily'][0].update(open='50',close='50',low='49')
    assert reason in measure(i['candles'],i['daily'],symbol='TEST',now=NOW)['blockers']


def environment(tmp_path):
    t=[NOW]; price=[None]; events=MemoryEvents()
    observer=SimpleNamespace(fetch=lambda ds: ([{'packet_id':d['packet_id'],
        'quote':{'observed_at':t[0].isoformat(),'bid':price[0],'ask':price[0]},'source':'alpaca_iex:'+'a'*64} for d in ds],[]))
    w=MethodShadow(tmp_path/'one',client=events,observer=observer,clock=lambda:t[0])
    return w,t,price,events


def test_enrol_fill_exit_restore_and_same_day_no_retry(tmp_path):
    w,t,price,events=environment(tmp_path); i=fixture()
    assert w.enrol(i,now=t[0])==[]
    plan=next(iter(w.cohorts.values()))['plan']; price[0]=plan['entry_eur']
    t[0]+=timedelta(seconds=2); w.poll(); assert w.outcomes(t[0])[0]['state']=='open_simulation'
    price[0]=plan['target_eur']; t[0]+=timedelta(seconds=2); w.poll()
    report=w.close(); assert report['results']['closed']==1 and report['results']['wins']==1
    assert w.enrol(i,now=t[0])==['already_enrolled_this_session']
    other=MethodShadow(tmp_path/'two',client=events,clock=lambda:t[0]); other.sync()
    assert other.outcomes(t[0])==w.outcomes(t[0])
    restored=MethodShadow(tmp_path/'restored',client=events,clock=lambda:t[0])
    for line in w.journal.read_text().splitlines(): restored.apply(json.loads(line))
    assert restored.outcomes(t[0])==w.outcomes(t[0])
    assert report['model_calls']==0 and report['ai_cost_eur']=='0'


def test_late_receipt_cannot_backdate_entry_or_exit(tmp_path):
    w,t,price,events=environment(tmp_path); w.enrol(fixture(),now=t[0])
    plan=next(iter(w.cohorts.values()))['plan']
    quote={'candidate_id':'stocks:TEST','source':'alpaca_iex:'+'a'*64,
        'quote':{'observed_at':(NOW+timedelta(seconds=55)).isoformat(),'bid':plan['entry_eur'],'ask':plan['entry_eur']},
        'received_at':(NOW+timedelta(seconds=61)).isoformat()}
    events.append(PROTOCOL_ID,[envelope('quote',quote,NOW+timedelta(seconds=61))]); w.sync()
    assert w.outcomes(NOW+timedelta(seconds=62))[0]['state']=='not_filled'
    # A distinct cohort projection with an actual entry, then quote after cutoff.
    w2,t2,price2,e2=environment(tmp_path/'second');w2.enrol(fixture(),now=NOW)
    t2[0]+=timedelta(seconds=1);price2[0]=plan['entry_eur'];w2.poll()
    t2[0]=datetime.fromisoformat(plan['exit_by'])+timedelta(seconds=1);w2.poll()
    assert w2.outcomes(t2[0])[0]['state']=='unresolved'


def test_failed_storage_and_corrupt_or_other_protocol_events(tmp_path):
    w,t,price,events=environment(tmp_path);events.fail=True
    with pytest.raises(RuntimeError): w.enrol(fixture(),now=NOW)
    assert not w.cohorts
    events.fail=False;w.enrol(fixture(),now=NOW)
    e=deepcopy(events.events[0]);e['experiment_id']='b'*64
    other=MethodShadow(tmp_path/'other',client=events,clock=lambda:NOW)
    with pytest.raises(ValueError):other.apply(e)
    e=deepcopy(events.events[0]);e['payload_json']='{}'
    with pytest.raises(ValueError):other.apply(e)


def test_entry_spread_guard_does_not_hide_open_position_stop():
    p=_plan(scenario(fixture(),now=NOW)['plan']); expiry=NOW+timedelta(seconds=60)
    def q(seconds,bid,ask):return Quote(observed_at=NOW+timedelta(seconds=seconds),bid=bid,ask=ask)
    qs=[q(1,p.entry-Decimal('.3'),p.entry),q(2,p.entry,p.entry),q(3,p.stop-1,p.entry+1)]
    out=replay_long(p,qs,decision_at=NOW,entry_expires_at=expiry,entry_mode='breakout',
        maximum_entry_spread_bps=Decimal(20),maximum_entry_gap_bps=Decimal(20))
    assert out.entry_at==NOW+timedelta(seconds=2) and out.reason=='stop'
    gap=replay_long(p,[q(1,p.entry*Decimal('1.003'),p.entry*Decimal('1.003'))],decision_at=NOW,
        entry_expires_at=expiry,entry_mode='breakout',maximum_entry_gap_bps=Decimal(20))
    assert gap.reason=='trigger_gap_exceeds_protocol_limit'
