from decimal import Decimal
from datetime import timedelta
import pytest
from test_candidate_packages import capture, NOW
from market_radar_ai.agents.combined_input import build_market_evidence
from market_radar_ai.agents.candidate_plan import draft


def test_generic_crypto_eur_risk_and_ordered_levels():
    d=capture()
    for row in d['captures']:
        bars=build_market_evidence(d,symbol=row['requested_symbol'],now=NOW,market_name='crypto')
        p=draft(bars,None,now=NOW)
        assert p['symbol']==row['requested_symbol'] and Decimal(p['planned_loss_eur']) <= 20
        assert Decimal(p['stop_eur']) < Decimal(p['entry_eur']) < Decimal(p['target_eur'])
        assert not p['trade_authorized'] and p['fx_rate']=='1'
        assert p['exit_by'].startswith(NOW.date().isoformat())


def test_after_cutoff_and_weekend_no_plan():
    d=capture();bars=build_market_evidence(d,symbol=d['captures'][0]['requested_symbol'],now=NOW,market_name='crypto')
    assert draft(bars,None,now=NOW.replace(hour=22)) is None
    weekend=NOW+timedelta(days=(5-NOW.weekday())%7)
    assert draft(bars,None,now=weekend) is None

def test_v2_packet_reproduces_plan_and_agents_receive_it():
    from market_radar_ai.agents.candidate_packages import build_packages
    from market_radar_ai.agents.candidate_review import run
    from test_candidate_review import answer
    d=capture();d['paper_scenarios_enabled']=True
    record=build_packages(d,None,now=NOW)['packages'][0]
    assert record['package']['schema_version']=='candidate-evidence-package-v2'
    assert record['package']['plan']['currency']=='EUR'
    seen=[]
    def ask(stage,p,s):
        seen.append(p['snapshot']['plan'])
        return answer(stage,p,s)
    result=run(record,d,None,ask,clock=lambda:NOW)
    assert len(seen)==8 and all(p==record['package']['plan'] for p in seen)
    assert not result['trade_authorized']
    record['package']['plan']['planned_loss_eur']='1'
    from market_radar_ai.agents.candidate_packages import digest
    record['package_id']=digest(record['package'])
    with pytest.raises(ValueError):run(record,d,None,ask,clock=lambda:NOW)


def test_usd_conversion_and_stale_fx_rejection():
    d=capture();b=build_market_evidence(d,symbol=d['captures'][0]['requested_symbol'],now=NOW,market_name='crypto')
    b=b.model_copy(update={'quote_currency':'USD','candles':tuple(c.model_copy(update={'quote_currency':'USD'}) for c in b.candles)})
    fx={'native_currency':'USD','eur_per_unit':'0.9','observed_at':NOW.isoformat(),'source':'test'}
    p=draft(b,fx,now=NOW)
    assert p['fx_rate']=='0.9' and Decimal(p['planned_loss_eur'])<=20
    fx['observed_at']=(NOW-timedelta(seconds=901)).isoformat()
    with pytest.raises(ValueError):draft(b,fx,now=NOW)
