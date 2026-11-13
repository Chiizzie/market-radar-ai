import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
import pytest
from market_radar_ai.agents.candidate_packages import digest, canonical
from market_radar_ai.agents.manual_execution_profile import validate_profile
from market_radar_ai.agents.manual_alert_evidence import (
    EXPERIMENT, PROTOCOL, PROFILE_PATH, record_ack, validate_clock, evaluate, read_clocks,
)

NOW = datetime(2026, 11, 16, 15, tzinfo=UTC)
PROFILE = validate_profile(json.loads(PROFILE_PATH.read_text()))


def fixture():
    plan = {'entry_eur': '100', 'stop_eur': '99', 'target_eur': '105',
            'expires_at': (NOW+timedelta(minutes=4)).isoformat(),
            'exit_by': (NOW+timedelta(hours=1)).isoformat()}
    body = {'candidate_id': 'stocks:TEST', 'sources': {}, 'plan': plan,
            'assembled_at': NOW.isoformat()}
    d = {'verdict': 'PAPER_WATCH_FOR_ENTRY', 'candidate_id': 'stocks:TEST',
         'evaluated_at': NOW.isoformat(), 'plan': plan}
    archive = {'decision': d, 'packet_id': digest(body), 'packet_json': canonical(body)}
    client = Mock()
    record_ack(archive, request_started_at=NOW, acknowledged_at=NOW,
               provider_date=int(NOW.timestamp()), recorded_at=NOW, client=client)
    event = client.append.call_args.args[1][0]
    clock = {**event, 'received_at': NOW.isoformat()}
    source = [{'seq': 1, 'kind': 'review', 'occurred_at': NOW.isoformat(),
        'received_at': NOW.isoformat(), 'payload_json': canonical({'packet': {
            'packet': body, 'packet_id': digest(body)}, 'decision': d})}]
    return archive, clock, source


def quote(seq, seconds, bid='100', ask='100.1', received=None):
    at = NOW+timedelta(seconds=seconds)
    return {'seq': seq, 'kind': 'quote', 'occurred_at': (received or at).isoformat(),
        'received_at': (received or at).isoformat(), 'payload_json': canonical({
            'candidate_id': 'stocks:TEST', 'quote': {'bid': bid, 'ask': ask, 'observed_at': at.isoformat()}})}


def test_acknowledgement_records_no_chat_message_id_or_human_receipt():
    _, c, _ = fixture(); p = validate_clock(json.loads(c['payload_json']))
    assert digest(PROTOCOL) == EXPERIMENT
    assert p['clock_basis'] == 'telegram_server_acknowledgement_not_device_receipt'
    assert p['device_receipt_observed'] is False and 'chat_id' not in p and 'message_id' not in p


def test_actual_clock_binding_and_declared_delay_price_feasibility():
    _, c, source = fixture()
    r = evaluate([c], source+[quote(2, 60), quote(3, 180)], PROFILE, now=NOW+timedelta(minutes=6))
    assert [s['state'] for s in r['details'][0]['scenarios']] == [
        'eligible_reference_quote_observed', 'eligible_reference_quote_observed', 'expired_before_response']
    assert not r['portfolio_evaluated'] and not r['broker_executable'] and not r['costs_verified']


def test_missing_clock_is_unknown_when_source_was_not_read():
    r = evaluate([], [], PROFILE, now=NOW, source_loaded=False)
    assert r['state'] == 'no_confirmed_alert_clocks'
    assert r['approved_reviews_without_clock'] is None
    assert r['source_loaded'] is False


def test_missing_source_review_is_counted_instead_of_inventing_a_plan():
    _, c, _ = fixture()
    r = evaluate([c], [], PROFILE, now=NOW+timedelta(minutes=6))
    assert r['unmatched_clocks'] == 1
    assert all(s['state']=='source_review_missing' for s in r['details'][0]['scenarios'])


@pytest.mark.parametrize('bid,ask', [('101', '101'), ('100', '101'), ('99.5', '99.6')])
def test_wrong_price_chasing_or_wide_quotes_do_not_count_as_entries(bid,ask):
    _, c, source = fixture()
    r = evaluate([c], source+[quote(2, 60, bid, ask)], PROFILE, now=NOW+timedelta(minutes=6))
    assert r['details'][0]['scenarios'][0]['state'] == 'no_eligible_quote_observed'


def test_stop_invalidation_before_response_is_retained_after_recovery():
    _, c, source = fixture()
    r = evaluate([c], source+[quote(2, 30, '98.9', '99'), quote(3, 60)], PROFILE,
                 now=NOW+timedelta(minutes=6))
    assert r['details'][0]['scenarios'][0]['state'] == 'invalidated_before_entry'


def test_stale_or_pre_response_quote_cannot_fill_after_late_receipt():
    _, c, source = fixture()
    r = evaluate([c], source+[quote(2, 10, received=NOW+timedelta(seconds=80))], PROFILE,
                 now=NOW+timedelta(minutes=6))
    assert r['details'][0]['scenarios'][0]['state'] == 'no_eligible_quote_observed'


def test_durable_receipt_delay_is_respected_and_future_clock_not_used():
    _, c, source = fixture(); c['received_at'] = (NOW+timedelta(seconds=90)).isoformat()
    r = evaluate([c], source+[quote(2, 60)], PROFILE, now=NOW+timedelta(minutes=6))
    assert r['details'][0]['scenarios'][0]['ready_at'] == c['received_at']
    assert r['details'][0]['scenarios'][0]['state'] == 'no_eligible_quote_observed'
    assert evaluate([c], source, PROFILE, now=NOW)['clocks'] == 0


def test_changed_plan_or_duplicate_clock_fails_closed():
    _, c, source = fixture()
    bad = deepcopy(source); p=json.loads(bad[0]['payload_json']);p['decision']['plan']['entry_eur']='101'
    bad[0]['payload_json']=canonical(p)
    with pytest.raises(ValueError,match='binding'):
        evaluate([c],bad,PROFILE,now=NOW)
    with pytest.raises(ValueError,match='duplicate_manual_clock'):
        evaluate([c,c],source,PROFILE,now=NOW)


def test_clock_input_and_partition_validation():
    _, c, _ = fixture(); p=json.loads(c['payload_json'])
    for changed in ({'device_receipt_observed':True},{'protocol_id':'a'*64},
                    {'acknowledged_at':(NOW-timedelta(seconds=1)).isoformat()},
                    {'message_sent_at':(NOW+timedelta(minutes=1)).isoformat()}):
        with pytest.raises(ValueError):validate_clock({**p,**changed})
    client=Mock();client.read.return_value={'events':[{'seq':1,'kind':'quote','experiment_id':EXPERIMENT,'day':'2026-11-16','event_id':'a'*64,'occurred_at':NOW.isoformat(),'payload_json':c['payload_json']}],'next':1}
    with pytest.raises(ValueError):read_clocks(client,'2026-11-16')


def test_clock_storage_failure_never_sends_another_message(monkeypatch):
    from test_paper_verdict import fixture as paper_fixture, NOW as old_now
    from test_scheduled_review import ENV
    from market_radar_ai.agents.paper_verdict import finalize,export_archive
    from market_radar_ai.dashboard.paper_final_delivery import deliver
    _,packet,audit,_=paper_fixture(monkeypatch)
    archive=export_archive(packet,audit,finalize(packet,audit,{},None,now=old_now))
    import market_radar_ai.agents.scheduled_review as scheduled
    monkeypatch.setattr(scheduled,'permitted',lambda *a:True)
    import market_radar_ai.agents.manual_alert_evidence as module
    monkeypatch.setattr(module,'record_ack',Mock(side_effect=RuntimeError('storage unavailable')))
    import hashlib
    calls=[]
    def post(url,**kw):
        calls.append(url)
        if 'telegram.org' in url:return Mock(status_code=200,json=lambda:{'ok':True,'result':{'chat':{'id':123},'message_id':1}})
        return Mock(status_code=200,json=lambda:{'ok':True,'archive_id':hashlib.sha256(kw['data']).hexdigest()})
    env={**ENV,'SEND_CANDIDATE_REVIEW':'true','SEND_SCHEDULED_TELEGRAM':'true','RECORD_MANUAL_ALERT_CLOCK':'true','REVIEW_INGEST_SECRET':'s'*32,'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'123'}
    r=deliver(archive,env=env,clock=lambda:old_now,session=Mock(post=post),ledger=Mock())
    assert len(calls)==2 and r['telegram']=='paper_notification_confirmed'
    assert r['manual_evidence']['state']=='manual_clock_unconfirmed_no_notification_retry'
