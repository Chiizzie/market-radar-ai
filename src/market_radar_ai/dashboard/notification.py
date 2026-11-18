"""Plain-text research notification preview. No network access or delivery."""
from datetime import datetime
from decimal import Decimal
import re
from zoneinfo import ZoneInfo
from .plan_review import aware

STAGES = ['opportunity_hunter','technical_analyst','news_analyst','devils_advocate',
          'risk_manager','final_decision','debate','conclusion']
VERDICTS = {'REJECT','MORE_EVIDENCE_REQUIRED','CONDITIONALLY_COHERENT'}


def render_review(review, *, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    if (review['schema_version']!='paper-review-dashboard-v1'
        or review['mode']!='HISTORICAL_PAPER_REVIEW'
        or review['trade_authorized'] is not False
        or review['live_orders_enabled'] is not False
        or review['review_status']!='COMPLETED_UNAPPROVED'
        or review.get('fixture',False) is not False):
        raise ValueError('not_real_unapproved_review')
    reports=review['reviews']
    if [r['stage'] for r in reports]!=STAGES:
        raise ValueError('incomplete_stages')
    if any(r['verdict'] not in VERDICTS for r in reports):
        raise ValueError('invalid_verdict')
    verdict=review['final_verdict']
    if verdict!=reports[-1]['verdict']:
        raise ValueError('verdict_mismatch')
    symbol=review['plan']['symbol']; identity=review['snapshot_id']
    if not re.fullmatch(r'[A-Z0-9.-]{1,15}',symbol) or not re.fullmatch(r'[a-f0-9]{64}',identity):
        raise ValueError('invalid_identity')
    expiry=aware(review['expires_at']);completed=aware(review['review_completed_at'])
    if not aware(review['evaluated_at'])<=completed<expiry or completed>now:
        raise ValueError('invalid_timing')
    cost=Decimal(review['estimated_review_cost_eur'])
    if not cost.is_finite() or not 0<=cost<=100:
        raise ValueError('invalid_cost')
    fmt=lambda t:t.astimezone(ZoneInfo('Europe/Dublin')).strftime('%d %b %Y %H:%M:%S')
    text='\n'.join(['MARKET RADAR AI — RESEARCH ONLY',
        f'{symbol}: {verdict.replace("_"," ")}',
        'Completed but unapproved — NOT A TRADE CALL.',
        'Six specialists + debate + conclusion completed.',
        f'Reviewed: {fmt(completed)} Dublin',
        f'Original expiry: {fmt(expiry)} Dublin',
        'EXPIRED — historical record only.' if now>=expiry else 'Historical research record; no entry authorization.',
        f'Estimated AI cost: €{cost}',
        'Broker, execution and catalyst evidence must still satisfy the decision policy.',
        f'Review ID: {identity}'])
    return {'version':'research-notification-preview-v1','delivery_enabled':False,
            'deduplication_key':'research:'+identity,'text':text}
