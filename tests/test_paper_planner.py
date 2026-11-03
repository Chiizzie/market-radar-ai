from datetime import datetime,timedelta,timezone
from decimal import Decimal
from market_radar_ai.agents.paper_planner import draft_nvda

NOW=datetime(2026,11,3,17,tzinfo=timezone.utc)
def inputs():
    rows=[dict(symbol='NVDA',interval='5m',timestamp=NOW-timedelta(minutes=5*(20-i)),open='100',high='102',low='99',close='101',volume='500',quote_currency='USD',source='yahoo_finance') for i in range(20)]
    cat=dict(state='catalogue_received',observed_at=NOW.isoformat(),candidates=[dict(ticker='NVDA_US_EQ',isin='US67066G1040',type='STOCK',currencyCode='USD',exchanges=[{'name':'NASDAQ'}])])
    fx=dict(native_currency='USD',eur_per_unit='0.9',observed_at=NOW,source='fixture')
    return rows,cat,fx

def run(args,now=NOW):return draft_nvda(*args,now=now,paper_capital_eur=500,round_trip_cost_bps=40)

def test_draft_cost_inclusive_risk_cap_and_no_authorization():
    r=run(inputs());p=r['plan']
    assert r['state']=='conditional_paper_draft' and r['trade_authorized'] is False
    q=Decimal(p['quantity']);entry=Decimal(p['entry_eur']);stop=Decimal(p['stop_eur']);cost=Decimal(p['assumed_round_trip_cost_eur'])
    loss=(entry-stop)*q+cost
    assert loss==Decimal(p['planned_loss_eur']) and loss<=20
    assert entry*q+cost<=500
    assert (Decimal(p['target1_eur'])-entry)*q-cost==2*loss
    assert len(r['blockers'])==5

def test_stale_catalogue_fx_and_wrong_identity_block():
    for what in ['catalogue','fx','identity','history']:
        rows,cat,fx=inputs()
        if what=='catalogue':cat['observed_at']=(NOW-timedelta(hours=1)).isoformat()
        if what=='fx':fx['observed_at']=NOW-timedelta(hours=1)
        if what=='identity':cat['candidates'][0]['isin']='leveraged-product'
        if what=='history':rows=rows[:3]
        assert run((rows,cat,fx))['plan'] is None

def test_cutoff_and_future_candle_block():
    assert run(inputs(),NOW.replace(hour=22))['plan'] is None
    args=inputs();args[0][-1]['timestamp']=NOW
    assert run(args)['plan'] is None
