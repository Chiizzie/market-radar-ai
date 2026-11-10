import json
import sqlite3
from copy import deepcopy
from datetime import timedelta
import pytest
from test_comparison_live import environment
from test_stock_checks import payload, NOW
from market_radar_ai.agents.comparison_live import LiveComparison,envelope
from market_radar_ai.agents.watcher_diagnostics import record_failure
from market_radar_ai.market_data.stock_checks import assess


def test_invalid_page_rolls_back_projection_cursor_and_export(tmp_path,monkeypatch):
    original,p,_,t,_,client=environment(tmp_path,monkeypatch)
    original.enrol(p,now=t[0])
    client.append(original.experiment,[envelope('quote',{'candidate_id':'stocks:NOTENROLLED',
        'quote':{'observed_at':t[0].isoformat(),'bid':'10','ask':'10'},
        'source':'test','received_at':t[0].isoformat()},t[0])])
    restored=LiveComparison(tmp_path/'bad',client=client,clock=lambda:t[0])
    with pytest.raises(ValueError,match='observe_only_after'):restored.sync()
    assert restored.cursor==0 and not restored.seen
    assert not (restored.root/'comparison-events.jsonl').exists()
    with sqlite3.connect(restored.store.path) as db:
        assert db.execute('SELECT COUNT(*) FROM comparison_cohort').fetchone()[0]==0


def test_page_replay_matches_individual_replay_and_exports_exact_events(tmp_path,monkeypatch):
    s,p,_,t,_,client=environment(tmp_path,monkeypatch)
    s.enrol(p,now=t[0]);t[0]+=timedelta(seconds=1);s.poll()
    batch=LiveComparison(tmp_path/'batch',client=client,clock=lambda:t[0])
    single=LiveComparison(tmp_path/'single',client=client,clock=lambda:t[0])
    batch.sync()
    for event in client.events:single.apply(event)
    assert batch.store.report(now=t[0])==single.store.report(now=t[0])
    assert (batch.root/'comparison-events.jsonl').read_bytes()==(single.root/'comparison-events.jsonl').read_bytes()
    assert batch.health['initial_sync']['events']==2
    before=(batch.root/'comparison-events.jsonl').read_bytes();batch.sync()
    assert before==(batch.root/'comparison-events.jsonl').read_bytes()


@pytest.mark.parametrize('fault,reason',[('missing','missing_quote'),('stale','stale_quote'),
 ('future','future_quote'),('crossed','crossed_quote'),('zero','nonpositive_or_nonfinite_quote'),
 ('currency','wrong_currency'),('malformed','malformed_quote')])
def test_quote_failure_reasons_preserve_gate(fault,reason):
    data=payload();q=data['quotes']['quotes']['IBM']
    if fault=='missing':data['quotes']['quotes']={}
    if fault=='stale':q['t']=(NOW-timedelta(seconds=31)).isoformat()
    if fault=='future':q['t']=(NOW+timedelta(seconds=1)).isoformat()
    if fault=='crossed':q['bp']=102
    if fault=='zero':q['as']=0
    if fault=='currency':data['quotes']['currency']='EUR'
    if fault=='malformed':q['t']='not a timestamp'
    row=assess(data,now=NOW)['stocks'][0]
    assert row['quote_status']=='unavailable' and row['quote_failure_reason']==reason
    assert 'indicative_bid_eur' not in row


def test_diagnostics_are_bounded_and_do_not_copy_arbitrary_text():
    health={}
    for _ in range(25):record_failure(health,'stock_quote_unavailable:IBM:stale_quote',NOW)
    assert len(health['recent_quote_failures'])==20
    assert health['last_failure']['symbol']=='IBM'
    record_failure(health,'stock_quote_unavailable:IBM:secret-provider-body',NOW)
    assert 'secret' not in json.dumps(health)
    assert 'symbol' not in health['last_failure']
