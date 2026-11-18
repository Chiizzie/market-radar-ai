from copy import deepcopy
import pytest
from market_radar_ai.dashboard.diagnostics import build_diagnostics
from test_stock_context import document,NOW


def empty_report():
    return {'schema_version':'paper-tracking-v1','as_of':NOW.isoformat(),'trades':[],
            'model_calls':0,'trade_authorized':False,'note':'Reference-quote simulation only.'}


def test_exports_real_empty_journal_distinct_from_missing():
    doc=document()
    assert build_diagnostics(doc,now=NOW)['paper_tracking'] is None
    doc['paper_tracking_report']=empty_report()
    report=build_diagnostics(doc,now=NOW)
    assert report['paper_tracking']['trades']==[]
    assert report['early_screening']['candidates'][0]['state']=='PREMARKET_RESEARCH'


def test_unknown_private_or_paid_fields_cannot_leak():
    doc=document();doc['paper_tracking_report']=empty_report()
    for key,value in [('secret','hidden'),('model_calls',1),('trade_authorized',True)]:
        altered=deepcopy(doc);altered['paper_tracking_report'][key]=value
        with pytest.raises(ValueError):build_diagnostics(altered,now=NOW)


def test_old_journal_is_not_redated():
    from datetime import timedelta
    doc=document();doc['paper_tracking_report']=empty_report()
    with pytest.raises(ValueError):build_diagnostics(doc,now=NOW+timedelta(minutes=6))
