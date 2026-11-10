"""Bounded diagnostics: never copy provider bodies, URLs or credentials."""
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
