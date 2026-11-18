from copy import deepcopy
from datetime import UTC, datetime, timedelta
from market_radar_ai.dashboard.scheduled_collection import review_can_continue


def report():
    return {'stages':{k:'ok' for k in ['news','market','context','calendar','stock_checks',
        'quotes','context_packages','readiness','qualification','paper_packets','dashboard']},
        'failures':[], 'delivery':{'state':'scanner_snapshot_delivery_confirmed',
        'coverage':{'stocks':{'current':12},'crypto':{'current':0}}}}


def test_crypto_outage_can_route_current_stocks_without_hiding_failure():
    r=report();r['stages']['market']='failed';r['failures']=['market'];original=deepcopy(r)
    assert review_can_continue(r) and r==original


def test_no_current_market_or_incomplete_pipeline_cannot_route():
    r=report();r['delivery']['coverage']['stocks']['current']=0
    assert not review_can_continue(r)
    for key in report()['stages']:
        r=report();del r['stages'][key]
        assert not review_can_continue(r)
    for key in ['news','calendar','stock_checks','quotes','qualification','dashboard']:
        r=report();r['stages'][key]='failed';assert not review_can_continue(r)
    r=report();r['failures']=['calendar_unavailable'];assert not review_can_continue(r)
    r=report();r['delivery']['state']='unconfirmed';assert not review_can_continue(r)


def test_late_confirmations_and_captures_expiring_before_handoff_block_review():
    original = report()
    deadline = datetime(2026, 11, 18, 22, 37, tzinfo=UTC)
    assert not review_can_continue(original, now=deadline)
    original['delivery'].update(expires_at_epoch=int(deadline.timestamp()), acknowledged_before_expiry=True)
    assert review_can_continue(original, now=deadline - timedelta(microseconds=1))
    assert not review_can_continue(original, now=deadline)
    original['delivery']['acknowledged_before_expiry'] = False
    assert not review_can_continue(original)
