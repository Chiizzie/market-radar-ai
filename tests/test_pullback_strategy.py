from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import json
import pytest

from market_radar_ai.market_data.models import Candle, ProviderResult
from market_radar_ai.market_data.pullback import detect_pullback, STRATEGY
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.agents.combined_input import MarketEvidence
from market_radar_ai.agents.setup_checks import technical_checks, validate_paper_plan
from market_radar_ai.agents.candidate_plan import draft
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.chart_news import checked_source
from market_radar_ai.agents.qualification import qualify
from market_radar_ai.agents.paper_verdict import build_packets, review, finalize, paper_gate
from market_radar_ai.evidence.alpaca_news import parse_alpaca_news
from market_radar_ai.evidence.combine import combine_feeds


def archived():
    record = json.loads((Path(__file__).parent/'fixtures/ash-2026-11-06-yahoo-replay.json').read_text())
    now = datetime.fromisoformat(record['captured_at'])
    rows = [Candle(symbol='ASH', interval='5m', timestamp=r[0], open=str(r[1]), high=str(r[2]),
                   low=str(r[3]), close=str(r[4]), volume=str(r[5]), quote_currency='USD',
                   source='yahoo_archive_replay') for r in record['bars']]
    return rows, now


def test_archived_ash_reclaim_reproduces_without_relabelling_it_as_iex():
    rows, now = archived()
    found = detect_pullback(rows, now=now)
    assert found['strategy_id'] == STRATEGY
    assert Decimal(found['reclaim_native']) == Decimal('77.61000061035156')
    assert Decimal(found['stop_native']) == Decimal('77.1801986694336')
    assert Decimal(found['target_cap_native']) == Decimal('79.5')
    # Use only the last 24 contiguous archived bars for the strict evidence
    # model. Earlier Yahoo session gaps remain recorded in the fixture.
    bars = MarketEvidence(symbol='ASH', provider='yahoo_archive_replay', retrieved_at=now,
        validated_at=now, original_capture_sha256='a'*64, quote_currency='USD', candles=rows[-24:])
    checks = technical_checks(bars, market='stocks')
    assert checks['strategy_id'] == STRATEGY and checks['trigger_state'] == 'WAITING_FOR_TRIGGER'
    assert Decimal(checks['relative_volume_5_vs_15']) > 6.6
    plan = draft(bars, {'native_currency':'USD','eur_per_unit':'.8969',
                       'observed_at':now.isoformat(),'source':'archived_replay_only'}, now=now, market='stocks')
    assert Decimal(plan['target_eur']) <= Decimal('79.5')*Decimal('.8969')
    # Catching the pattern must not inflate resistance or weaken the 40bps/2R rule.
    assert 'net_reward_below_2r' in validate_paper_plan(plan, now=now)['failures']


@pytest.mark.parametrize('fault', ['gap','unfinished','stale','overnight','broken_support','no_reclaim'])
def test_incomplete_or_broken_pullbacks_never_form_a_pattern(fault):
    rows, now = archived(); rows=rows[-24:]
    if fault=='gap': rows.pop(-8)
    elif fault=='unfinished': now=rows[-1].timestamp+timedelta(minutes=4)
    elif fault=='stale': now+=timedelta(minutes=15)
    elif fault=='overnight': rows[0]=rows[0].model_copy(update={'timestamp':rows[0].timestamp-timedelta(days=1)})
    elif fault=='broken_support': rows[-1]=rows[-1].model_copy(update={'low':Decimal('74')})
    elif fault=='no_reclaim': rows[-1]=rows[-1].model_copy(update={'close':Decimal('77.52')})
    assert detect_pullback(rows,now=now) is None


def empty_feed(symbol, now):
    raw=parse_alpaca_news({'news':[]},symbol=symbol,now=now,start=now-timedelta(days=7))
    return combine_feeds([raw],now=now)


@pytest.mark.parametrize('fault', ['missing','outage','stale','wrong_symbol','bad_items','discarded_articles'])
def test_no_catalyst_is_distinct_from_an_unperformed_or_incomplete_news_check(fault):
    _, now=archived(); feed=empty_feed('TEST',now)
    assert checked_source(feed,symbol='TEST',now=now)
    if fault=='missing': feed['sources']=[]
    elif fault=='outage': feed['sources'][0]['status']='error'
    elif fault=='stale': feed['sources'][0]['retrieved_at']=(now-timedelta(seconds=901)).isoformat()
    elif fault=='wrong_symbol': feed['sources'][0]['query_symbol']='OTHER'
    elif fault=='bad_items': feed['sources'][0]['rejected_item_count']=1
    else:
        feed['sources'][0].update(validated_evidence_ids=['not_retained'],validated_item_count=1,response_item_count=1)
    assert checked_source(feed,symbol='TEST',now=now) is None


def synthetic_setup():
    rows, now=archived()
    # Fictional variant for pipeline testing, NOT the recorded ASH outcome:
    # a higher impulse peak supplies enough observed target room after costs.
    rows=[c.model_copy(update={'symbol':'TEST','source':'alpaca_iex',
            'high':Decimal('80') if c.high==Decimal('79.5') else c.high}) for c in rows[-24:]]
    result=ProviderResult(provider='alpaca_iex',retrieved_at=now,candles=rows)
    doc=capture_markets(['TEST'],[],stock_fetch=lambda s:result,crypto_fetch=None,
                        stock_provider='alpaca_iex',now=now)
    reference={'schema_version':'stock-reference-checks-v1','symbols':['TEST'],'trade_authorized':False,
        'retrieved_at':now.isoformat(), 'market_clock':{'timestamp':now.isoformat(),'is_open':True,
            'next_open':(now+timedelta(days=3)).isoformat(),'next_close':now.replace(hour=21,minute=0).isoformat()},
        'quotes':{'quotes':{'TEST':{'t':now.isoformat(),'bp':77.63,'ap':77.65,'bs':3,'as':4}}},
        'fx':{'native_currency':'USD','eur_per_unit':'.9','source':'synthetic','observed_at':now.isoformat()},
        'catalogue_candidates':{'TEST':[{'ticker':'TEST_US_EQ','isin':'synthetic'}]}}
    doc['stock_reference_checks']={'payload':reference,'payload_sha256':digest(reference)}
    return doc, empty_feed('TEST',now), now


def test_separate_chart_strategy_reaches_all_six_reviewers_and_revalidates_before_watch(tmp_path):
    doc,feed,now=synthetic_setup()
    result=build_packets(doc,feed,now=now)
    assert len(result['packets'])==1
    packet=result['packets'][0]; body=packet['packet']
    assert body['technical_checks']['strategy_id']==STRATEGY
    assert not any(s.startswith('news:') for s in body['source_ids'])
    assert any(s.startswith('news_check:') for s in body['source_ids'])
    stages=[]
    def ask(stage,prompt,schema):
        stages.append(stage)
        assert prompt['packet']['technical_checks']['strategy_id']==STRATEGY
        return {'stage':stage,'packet_id':prompt['packet_id'],'verdict':'APPROVE_PAPER',
            'rationale':'Fictional paper pipeline test only','source_ids':[body['source_ids'][0]],
            'concerns':[],'reviewed_stages':[r['stage'] for r in prompt['peer_reviews']]}
    audit=review(packet,doc,feed,ask,clock=lambda:now)
    assert len(stages)==8
    decision=finalize(packet,audit,doc,feed,now=now)
    assert decision['verdict']=='PAPER_WATCH_FOR_ENTRY' and not decision['trade_authorized']
    assert STRATEGY in decision['plan']['trigger']
    from market_radar_ai.agents.paper_tracking import PaperTracker
    from market_radar_ai.agents.paper_outcomes import Quote
    tracker=PaperTracker(tmp_path/'synthetic-journal.sqlite')
    key=tracker.register(decision)
    for seconds, price in [(1, decision['plan']['entry_eur']), (10, decision['plan']['target_eur'])]:
        at=now+timedelta(seconds=seconds)
        tracker.observe(key,Quote(observed_at=at,bid=price,ask=price),symbol='TEST',source='synthetic',now=at)
    outcome=tracker.report(now=now+timedelta(seconds=10))['trades'][0]
    assert outcome['state']=='closed' and outcome['outcome']['entry_at'] is not None
    assert Decimal(outcome['outcome']['net_pnl_eur']) > 0  # fictional lifecycle only
    audit['reviews'][3]['verdict']='REJECT'
    assert finalize(packet,audit,doc,feed,now=now)['verdict']=='NO_ACTION'


def test_news_exemption_never_spills_into_momentum_crypto_or_bad_quotes():
    doc,feed,now=synthetic_setup(); row=qualify(doc,feed,now=now)['candidates'][0]
    assert paper_gate(row,now=now)['eligible_for_paper_review']
    momentum=deepcopy(row); momentum['technical_checks']['strategy_id']='momentum_20_bar_v1'
    assert 'current_symbol_linked_news_missing' in paper_gate(momentum,now=now)['paper_blockers']
    crypto=deepcopy(row);crypto['market']='crypto'
    assert 'stock_pullback_pattern_not_confirmed' in paper_gate(crypto,now=now)['paper_blockers']
    below=deepcopy(row);below['reference_checks']['indicative_bid_eur']=row['conditional_paper_plan']['stop_eur']
    assert 'setup_invalidated_before_entry' in paper_gate(below,now=now)['paper_blockers']
    assert not build_packets(doc,empty_feed('OTHER',now),now=now)['packets']


def test_comparison_records_chart_strategy_separately(tmp_path):
    from market_radar_ai.agents.paper_comparison import ComparisonStore
    doc,feed,now=synthetic_setup(); packet=build_packets(doc,feed,now=now)['packets'][0]
    store=ComparisonStore(tmp_path/'new-protocol.sqlite',dataset_kind='synthetic')
    store.enrol(packet,now=now)
    report=store.report(now=now)
    assert report['rows'][0]['strategy_id']==STRATEGY
    assert report['by_strategy'][STRATEGY]['cohort_count']==1
    assert report['by_strategy'][STRATEGY]['code_only']['closed']==0
