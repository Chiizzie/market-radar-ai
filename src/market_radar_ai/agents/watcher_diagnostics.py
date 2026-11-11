"""Bounded diagnostics: never copy provider bodies, URLs or credentials."""
import re
from datetime import datetime

QUOTE_REASONS = {'missing_quote','stale_quote','future_quote','crossed_quote',
                 'nonpositive_or_nonfinite_quote','wrong_currency','malformed_quote'}

CODES = {'paper_journal_rate_limited', 'paper_journal_unavailable',
         'stock_quote_unavailable', 'stock_reference_observation_unavailable',
         'crypto_reference_observation_unavailable', 'stale_comparison_quote',
         'stock_fx_unavailable', 'stock_clock_unavailable', 'stock_quotes_unavailable',
         'stock_validation_unavailable', 'invalid_comparison_event'}

def record_failure(health, failure, now):
    code = getattr(failure, 'diagnostic_code', None)
    if code not in {'storage_timeout','storage_transport','storage_http','storage_response'}:
        candidate = str(failure).split(':',1)[0]
        code = candidate if candidate in CODES else 'internal_validation_or_storage_error'
    counts = health.setdefault('failure_counts', {})
    counts[code] = counts.get(code, 0) + 1
    health.setdefault('first_failure_at', now.isoformat())
    health['last_failure_at'] = now.isoformat()
    health['last_failure'] = {'code': code}
    if hasattr(failure, 'attempts'): health['last_failure']['attempts'] = failure.attempts
    if getattr(failure, 'http_status', None) is not None:
        health['last_failure']['http_status'] = failure.http_status
    if code == 'stock_quote_unavailable':
        parts = str(failure).split(':')
        if len(parts)==3 and re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}',parts[1]) and parts[2] in QUOTE_REASONS:
            detail={'symbol':parts[1],'reason':parts[2],'at':now.isoformat()}
            health['last_failure'].update(detail)
            recent=health.setdefault('recent_quote_failures',[])
            recent.append(detail)
            del recent[:-20]
            if parts[2] in ('stale_quote','missing_quote'):
                gaps=health.setdefault('quote_gap_counts',{})
                gaps[parts[1]]=gaps.get(parts[1],0)+1
                health.setdefault('unrecovered_quote_gaps',{}).setdefault(parts[1],now.isoformat())


def record_quote_recovery(health, symbol, now):
    pending=health.get('unrecovered_quote_gaps',{})
    if symbol in pending:
        elapsed=(now-datetime.fromisoformat(pending[symbol])).total_seconds()
        if elapsed < 0: raise ValueError('quote_recovery_before_gap')
        health['maximum_quote_gap_seconds']=max(health.get('maximum_quote_gap_seconds',0),elapsed)
        health.setdefault('recovered_quote_gap_symbols',{})[symbol]=now.isoformat()
        del pending[symbol]


def recovered_quote_gaps(health):
    """Only small, recovered source-data gaps may be warnings, never an outage."""
    comparison=health.get('comparison',{})
    counts=comparison.get('failure_counts',{})
    soft=sum(comparison.get('quote_gap_counts',{}).values())
    return bool(soft and not health.get('failure_counts')
        and set(counts)=={'stock_quote_unavailable'} and counts['stock_quote_unavailable']==soft
        and not comparison.get('unrecovered_quote_gaps')
        and health.get('quotes_received',0)>0 and health.get('polls',0)>0
        and health['error_polls']/health['polls']<=.2
        and comparison.get('capacity_deferred',0)==0
        and comparison.get('maximum_quote_gap_seconds',0)<=30
        and max(health.get('maximum_poll_gap_seconds',0),comparison.get('maximum_poll_gap_seconds',0))<=15)
