from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest
from market_radar_ai.agents.paper_tracking import PaperTracker
from market_radar_ai.agents.paper_outcomes import Quote
from market_radar_ai.agents.paper_verdict import finalize
from test_paper_verdict import fixture, NOW


def tracker(tmp_path,monkeypatch):
    _,packet,audit,_=fixture(monkeypatch)
    decision=finalize(packet,audit,{},None,now=NOW)
    t=PaperTracker(tmp_path/'journal.sqlite');key=t.register(decision)
    return t,key,decision


def test_watch_entry_target_costs_and_restart(tmp_path,monkeypatch):
    t,key,d=tracker(tmp_path,monkeypatch);p=d['plan']
    assert t.report(now=NOW)['trades'][0]['state']=='watching'
    q=Quote(observed_at=NOW+timedelta(seconds=1),bid=p['entry_eur'],ask=p['entry_eur'])
    t.observe(key,q,symbol='TEST',source='fixture',now=q.observed_at)
    assert t.report(now=q.observed_at)['trades'][0]['state']=='open_simulation'
    q=Quote(observed_at=NOW+timedelta(seconds=2),bid=p['target_eur'],ask=p['target_eur'])
    t.observe(key,q,symbol='TEST',source='fixture',now=q.observed_at)
    t=PaperTracker(t.path)
    outcome=t.report(now=q.observed_at)['trades'][0]['outcome']
    assert outcome['status']=='closed' and outcome['reason']=='target'
    expected=(Decimal(p['target_eur'])-Decimal(p['entry_eur']))*Decimal(p['quantity'])-Decimal(p['assumed_round_trip_cost_eur'])
    assert Decimal(outcome['net_pnl_eur'])==expected


def test_immutable_decisions_quotes_and_identity(tmp_path,monkeypatch):
    t,key,d=tracker(tmp_path,monkeypatch)
    assert t.register(d)==key
    changed=deepcopy(d);changed['assumptions'].append('changed')
    with pytest.raises(ValueError):t.register(changed)
    q=Quote(observed_at=NOW,bid=d['plan']['entry_eur'],ask=d['plan']['entry_eur'])
    with pytest.raises(ValueError):t.observe(key,q,symbol='OTHER',source='fixture',now=NOW)
    with pytest.raises(ValueError):t.observe(key,q,symbol='TEST',source='fixture',now=NOW+timedelta(minutes=2))
    t.observe(key,q,symbol='TEST',source='fixture',now=NOW)
    t.observe(key,q,symbol='TEST',source='fixture',now=NOW)
    with pytest.raises(ValueError):t.observe(key,q,symbol='TEST',source='changed',now=NOW)
    assert t.report(now=NOW)['trades'][0]['quote_count']==1


def test_no_observation_does_not_invent_win(tmp_path,monkeypatch):
    t,key,d=tracker(tmp_path,monkeypatch)
    row=t.report(now=NOW+timedelta(days=1))['trades'][0]
    assert row['state']=='not_filled' and row['outcome']['net_pnl_eur'] is None
    d['verdict']='NO_ACTION'
    with pytest.raises(ValueError):t.register(d)


def test_capture_reuses_checked_eur_quotes_and_rejects_tampering(tmp_path,monkeypatch):
    from market_radar_ai.agents.paper_tracking import ingest_capture
    from market_radar_ai.agents.candidate_packages import digest
    from test_stock_checks import payload
    t,key,d=tracker(tmp_path,monkeypatch)
    p=payload();p['symbols']=['TEST'];p['catalogue_candidates']={'TEST':[]}
    p['retrieved_at']=NOW.isoformat();p['market_clock']['timestamp']=NOW.isoformat()
    p['market_clock']['next_close']=d['plan']['exit_by'];p['fx']['observed_at']=NOW.isoformat()
    entry=Decimal(d['plan']['entry_eur'])/Decimal('0.9')
    p['quotes']={'quotes':{'TEST':{'t':NOW.isoformat(),'bp':str(entry),'ap':str(entry),'bs':1,'as':1}}}
    doc={'stock_reference_checks':{'payload':p,'payload_sha256':digest(p)}}
    assert ingest_capture(t,doc,now=NOW)==1
    assert t.report(now=NOW)['trades'][0]['state']=='open_simulation'
    doc['stock_reference_checks']['payload_sha256']='tampered'
    with pytest.raises(ValueError):ingest_capture(t,doc,now=NOW)
