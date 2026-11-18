from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from market_radar_ai.market_data.strategy_window import profile
from market_radar_ai.market_data.crypto_checks import catalogue, enrich, assess, SCOPE
from market_radar_ai.market_data.providers.robinhood import RobinhoodEuropeCatalogue
from market_radar_ai.market_data.models import Candle, ProviderResult
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.agents.candidate_packages import digest
from market_radar_ai.agents.paper_verdict import build_packets, review, finalize
from market_radar_ai.agents.setup_checks import reference_checks
from test_evidence_enrichment import reference, news, NOW


def public(now=NOW):
    p={'source':RobinhoodEuropeCatalogue.URL,'scope':SCOPE,'retrieved_at':now.isoformat(),
       'assets':[{'symbol':'XRP','name':'XRP'}]}
    return {'payload':p,'payload_sha256':digest(p)}


def crypto_document():
    def fetch(symbol):
        rows=[Candle(symbol=symbol,interval='5m',timestamp=NOW-timedelta(minutes=5*(20-i)),
                     open=100,high=102,low=99,close=Decimal(100)+Decimal(i)/20,
                     volume=10 if i<15 else 20,quote_currency='EUR',source='kraken') for i in range(20)]
        return ProviderResult(provider='kraken',retrieved_at=NOW,candles=rows)
    doc=capture_markets([],['XRPEUR'],stock_fetch=None,crypto_fetch=fetch,now=NOW)
    doc['crypto_catalogue']=public()
    ref=reference();p=ref['payload'];p['tickers']['result']['XXRPZEUR']['a'][0]='100.3';p['tickers']['result']['XXRPZEUR']['b'][0]='100.2';ref['payload_sha256']=digest(p)
    doc['reference_quote_capture']=ref
    return doc


def approve(stage,prompt,schema):
    return dict(stage=stage,packet_id=prompt['packet_id'],verdict='APPROVE_PAPER',rationale='Synthetic test only',
                source_ids=[prompt['packet']['source_ids'][0]],concerns=[],reviewed_stages=[p['stage'] for p in prompt['peer_reviews']])


def test_crypto_full_qualification_review_refresh_and_tracking(tmp_path):
    from market_radar_ai.agents.paper_tracking import PaperTracker, ingest_capture
    d=crypto_document();batch=build_packets(d,news(),now=NOW)
    assert len(batch['packets'])==1, batch['qualification']['blocker_counts']
    packet=batch['packets'][0];checks=packet['packet']['reference_checks']
    assert checks['broker_account_permission']=='UNKNOWN' and checks['catalogue_candidate']=='PASS'
    assert any(k.startswith('catalogue:') for k in packet['packet']['sources'])
    assert datetime.fromisoformat(packet['packet']['plan']['expires_at'])==NOW+timedelta(seconds=30)
    audit=review(packet,d,news(),approve,clock=lambda:NOW)
    decision=finalize(packet,audit,d,news(),now=NOW)
    assert decision['verdict']=='PAPER_WATCH_FOR_ENTRY' and not decision['trade_authorized']
    tracker=PaperTracker(tmp_path/'journal.sqlite');tracker.register(decision)
    # A below-trigger poll changes no decision and need not grow the durable log.
    assert ingest_capture(tracker,d,now=NOW)==0
    row=tracker.report(now=NOW)['trades'][0]
    assert row['quote_count']==0 and row['state']=='watching'
    d['crypto_catalogue']['payload']['retrieved_at']=(NOW+timedelta(seconds=1)).isoformat()
    d['crypto_catalogue']['payload_sha256']=digest(d['crypto_catalogue']['payload'])
    assert finalize(packet,audit,d,news(),now=NOW+timedelta(seconds=1))['verdict']=='PAPER_WATCH_FOR_ENTRY'


@pytest.mark.parametrize('fault',['missing','stale','future','hash','wrong_source','wrong_scope','wrong_name','duplicate','quote_stale','quote_hash','offline','wrong_pair','news'])
def test_crypto_missing_or_mismatched_evidence_blocks_before_ai(fault):
    d=crypto_document();feed=news();r=d['crypto_catalogue'];p=r['payload']
    if fault=='missing':del d['crypto_catalogue']
    if fault=='stale':p['retrieved_at']=(NOW-timedelta(days=1)).isoformat()
    if fault=='future':p['retrieved_at']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='wrong_source':p['source']='https://example.com/list'
    if fault=='wrong_scope':p['scope']='account_verified'
    if fault=='wrong_name':p['assets'][0]['name']='Unrelated coin'
    if fault=='duplicate':p['assets']*=2
    r['payload_sha256']='bad' if fault=='hash' else digest(p)
    ref=d['reference_quote_capture']
    if fault=='quote_stale':ref['retrieved_at']=(NOW-timedelta(minutes=1)).isoformat()
    if fault=='offline':ref['payload']['asset_pairs']['result']['XXRPZEUR']['status']='maintenance'
    if fault=='wrong_pair':ref['payload']['asset_pairs']['result']['XXRPZEUR']['base']='BTC'
    ref['payload_sha256']='bad' if fault=='quote_hash' else digest(ref['payload'])
    if fault=='news':feed=news('<category>Bitcoin</category>')
    assert build_packets(d,feed,now=NOW)['packets']==[]


@pytest.mark.parametrize('stamp',['2026-11-07T12:00:00+00:00','2026-11-06T22:00:00+00:00','2026-11-06T07:59:59+00:00'])
def test_crypto_reference_window_closed(stamp):
    now=datetime.fromisoformat(stamp);d=crypto_document();ref=d['reference_quote_capture']
    ref['request_started_at']=ref['retrieved_at']=now.isoformat();d['crypto_catalogue']=public(now)
    assert assess(d,symbol='XRPEUR',now=now)['market_session']=='FAIL'


def test_catalogue_network_failure_is_explicit_and_never_uses_old_list():
    def fail():raise RuntimeError('secret')
    d=enrich(crypto_document(),fetch=fail,clock=lambda:NOW)
    assert d['crypto_catalogue']=={'status':'unavailable','trade_authorized':False}
    assert 'secret' not in str(d)
    assert reference_checks(d,symbol='XRPEUR',market='crypto',now=NOW)['catalogue_candidate']=='UNKNOWN'


def opening_rows(stamp='2026-11-06T15:00:00+00:00',count=6):
    now=datetime.fromisoformat(stamp)
    from zoneinfo import ZoneInfo
    opening=now.astimezone(ZoneInfo('America/New_York')).replace(hour=9,minute=30,second=0,microsecond=0)
    rows=[Candle(symbol='IBM',source='alpaca_iex',interval='5m',quote_currency='USD',timestamp=opening+timedelta(minutes=i*5),
                 open=100,high=102,low=99,close=Decimal(100)+Decimal(i)/10,volume=10 if i<3 else 20) for i in range(count)]
    return now,rows


@pytest.mark.parametrize('stamp',['2026-11-06T15:00:00+00:00','2026-03-10T14:00:00+00:00'])
def test_opening_six_bar_candidate_reaches_complete_paper_review(stamp):
    from test_stock_checks import payload
    from test_candidate_packages import feed
    now,rows=opening_rows(stamp)
    d=capture_markets(['IBM'],[],stock_fetch=lambda s:ProviderResult(provider='alpaca_iex',retrieved_at=now,candles=rows),crypto_fetch=None,now=now)
    p=payload();p['retrieved_at']=now.isoformat();p['market_clock']['timestamp']=now.isoformat()
    p['market_clock']['next_open']=(now+timedelta(days=1)).isoformat()
    p['market_clock']['is_open']=True;p['market_clock']['next_close']=(now+timedelta(hours=5)).isoformat()
    p['fx']['observed_at']=now.isoformat()
    p['quotes']['quotes']['IBM'].update(t=now.isoformat(),ap='100.6',bp='100.5')
    d['stock_reference_checks']={'payload':p,'payload_sha256':digest(p)}
    f=feed(('IBM',));f['retrieved_at']=now.isoformat()
    for item in f['items']:item['retrieved_at']=item['published_at']=now.isoformat()
    batch=build_packets(d,f,now=now)
    assert len(batch['packets'])==1,batch['qualification']['blocker_counts']
    packet=batch['packets'][0];tech=packet['packet']['technical_checks']
    assert tech['strategy_id']=='opening_continuation_30m_v1' and tech['completed_bars']==6
    assert tech['relative_volume_3_vs_prior']=='2' and 'momentum_20_bars_pct' not in tech
    audit=review(packet,d,f,approve,clock=lambda:now)
    assert finalize(packet,audit,d,f,now=now)['verdict']=='PAPER_WATCH_FOR_ENTRY'


@pytest.mark.parametrize('fault',['five','incomplete','gap','previous_day','premarket','delayed','weekend','late_missing_bars'])
def test_opening_window_never_borrows_missing_or_delayed_history(fault):
    now,rows=opening_rows()
    if fault=='five':rows=rows[:5]
    if fault=='incomplete':now-=timedelta(seconds=1)
    if fault=='gap':rows[2]=rows[2].model_copy(update={'timestamp':rows[2].timestamp+timedelta(minutes=5)})
    if fault=='previous_day':rows=[r.model_copy(update={'timestamp':r.timestamp-timedelta(days=1)}) for r in rows]
    if fault=='premarket':rows=[r.model_copy(update={'timestamp':r.timestamp-timedelta(minutes=30)}) for r in rows]
    if fault=='delayed':rows=[r.model_copy(update={'source':'alpaca_sip_delayed'}) for r in rows]
    if fault=='weekend':now,rows=opening_rows('2026-11-07T15:00:00+00:00')
    if fault=='late_missing_bars':now+=timedelta(minutes=70)
    assert profile(rows,now=now) is None
