import json
from copy import deepcopy
from datetime import timedelta
import pytest
from market_radar_ai.agents.trade_evaluation import fill_quote_quality
from test_trade_evaluation import row,quote,NOW

def q(seconds,bid,ask):
    event=quote(seconds,bid);p=json.loads(event['payload_json']);p['quote']['ask']=ask
    event['payload_json']=json.dumps(p);return event

@pytest.mark.parametrize('net,exit_bid,exit_ask',[('-22','95','105'),('2','101','111')])
def test_wide_exit_flags_losses_and_gains_without_rewriting(net,exit_bid,exit_ask):
    r=row(net=net,exit_seconds=10);original=deepcopy(r)
    report=fill_quote_quality([r],[q(0,'99.99','100'),q(10,exit_bid,exit_ask)],'code_only')
    assert report['checked_fills']==2 and report['wide_spread_fills']==1
    assert report['findings'][0]['side']=='exit' and report['requires_review']
    assert r==original and not report['outcomes_changed']

def test_no_nearest_quote_or_zero_spread_invented_for_missing_exact_fill():
    r=row(exit_seconds=10)
    report=fill_quote_quality([r],[q(0,'99.99','100'),q(9,'100','100.01'),q(11,'100','100.01')],'code_only')
    assert report['unavailable_fills']==1 and report['checked_fills']==1
    assert report['findings'][0]['side']=='exit'

@pytest.mark.parametrize('bid,ask',[('101','100'),('0','0'),('NaN','100')])
def test_invalid_fill_quote_is_unknown(bid,ask):
    report=fill_quote_quality([row(exit_seconds=10)],[q(0,'99.99','100'),q(10,bid,ask)],'code_only')
    assert report['unavailable_fills']==1 and report['checked_fills']==1

def test_repeated_identical_observation_is_not_an_ambiguity():
    events=[q(0,'99.99','100'),q(10,'100','100.01')]
    report=fill_quote_quality([row(exit_seconds=10)],events+events,'code_only')
    assert report['checked_fills']==2 and not report['requires_review']
