import json
from pathlib import Path
from datetime import datetime,timezone
import pytest
from market_radar_ai.dashboard.notification import render_review
NOW=datetime(2026,11,3,20,tzinfo=timezone.utc)

def real():return json.loads(Path('docs/dashboard/nvda-reviewed-plan-2026-11-03.json').read_text())

def test_real_historical_review_is_research_only():
    r=render_review(real(),now=NOW)
    assert 'EXPIRED' in r['text'] and 'NOT A TRADE CALL' in r['text']
    assert not r['delivery_enabled'] and len(r['text'])<4096
    assert render_review(real(),now=NOW)['deduplication_key']==r['deduplication_key']

@pytest.mark.parametrize('fault',['fixture','authorized','stages','verdict','symbol','cost'])
def test_unsafe_or_invalid_notification_rejected(fault):
    r=real()
    if fault=='fixture':r['fixture']=True
    if fault=='authorized':r['trade_authorized']=True
    if fault=='stages':r['reviews'].pop()
    if fault=='verdict':r['final_verdict']='BUY'
    if fault=='symbol':r['plan']['symbol']='NVDA\nBUY NOW'
    if fault=='cost':r['estimated_review_cost_eur']='NaN'
    with pytest.raises(ValueError):render_review(r,now=NOW)
