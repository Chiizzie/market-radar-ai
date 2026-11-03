"""Allowlisted historical review export; never an actionable signal."""
from datetime import datetime
from decimal import Decimal
import json
from ..agents.plan_review import prepare, run, canonical
from ..agents.alpaca_paper_rehearsal import build


def aware(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('aware_time_required')
    return t


def export_review(capture,catalogue,draft,audit,*,now):
    if now.tzinfo is None:raise ValueError('aware_time_required')
    if (audit['version']!='paid-paper-review-v1' or audit['state']!='completed'
            or audit['trade_authorized'] is not False or len(audit['calls'])!=8):
        raise ValueError('incomplete_review')
    packet=prepare(capture,catalogue,draft)
    # Revalidate the original timing, not today's clock; output is historical only.
    times=[];responses=[];cost=0
    previous=aware(draft['evaluated_at'])
    for call in audit['calls']:
        start,end=aware(call['started_at']),aware(call['received_at'])
        if call['state']!='received' or not previous<=start<=end<=now:
            raise ValueError('invalid_review_timing')
        amount=call['estimated_cost_microeur']
        if type(amount) is not int or amount<0:raise ValueError('invalid_cost')
        cost+=amount;previous=end;times.extend([start,end])
        response=call['untrusted_response']
        if response['stage']!=call['stage']:raise ValueError('stage_mismatch')
        responses.append(response)
    completed=aware(audit['completed_at'])
    if not previous<=completed<=now:raise ValueError('invalid_review_timing')
    timeline=iter(times);replies=iter(responses)
    accepted=run(packet,lambda *_:next(replies),clock=lambda:next(timeline))
    if canonical(accepted)!=canonical(audit['result']):raise ValueError('review_result_mismatch')
    # Rebuild rather than pass through arbitrary draft fields.
    clean=build(capture,catalogue,draft['fx_evidence'],now=aware(draft['evaluated_at']))
    clean.pop('quote_context',None);clean.pop('news_context',None)
    return dict(schema_version='paper-review-dashboard-v1',mode='HISTORICAL_PAPER_REVIEW',
        trade_authorized=False,live_orders_enabled=False,
        snapshot_id=accepted['snapshot_id'],evaluated_at=draft['evaluated_at'],
        review_completed_at=completed.isoformat(),expires_at=clean['plan']['expires_at'],
        expired=now>=aware(clean['plan']['expires_at']),
        plan=clean['plan'],assumptions_note=clean['assumptions_note'],
        input_blockers=accepted['blockers'],review_status='COMPLETED_UNAPPROVED',
        reviews=accepted['reviews'],final_verdict=accepted['reviews'][-1]['verdict'],
        estimated_review_cost_eur=str(Decimal(cost)/Decimal(1000000)),
        notice='Historical review only. Completion is not trade approval; evidence and model reasoning require review.')
