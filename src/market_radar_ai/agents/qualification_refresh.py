"""Refresh short-lived qualification inputs without restamping retained evidence."""
from copy import deepcopy
from datetime import datetime
from ..dashboard.api_budget import read_summary, validate_summary
from ..market_data.stock_checks import collect
from ..market_data.reference_quotes import capture_quotes, validate_capture


def refresh_current_inputs(document, *, env, clock, force=False):
    current = document
    changed = []
    def replace(key, value):
        nonlocal current
        if current is document: current = deepcopy(document)
        current[key] = value
        changed.append(key)
    # Ledger reads can be slow; perform them before fetching short-lived quotes.
    if 'api_budget' in document:
        try:
            validate_summary(document['api_budget'], now=clock())
            refresh_budget = force
        except (ValueError, KeyError, TypeError):
            refresh_budget = True
        if refresh_budget:
            replace('api_budget',read_summary(env.get('GH_BUDGET_TOKEN'),clock=clock))
    if 'reference_quote_capture' in document:
        try:
            validate_capture(document['reference_quote_capture'],now=clock())
            refresh_crypto = force
        except (ValueError, KeyError, TypeError, ArithmeticError):
            refresh_crypto = True
        if refresh_crypto:
            symbols=[r['requested_symbol'] for r in document.get('captures',[]) if r['market']=='crypto']
            if symbols:
                replace('reference_quote_capture',capture_quotes(symbols,clock=clock))
    if 'stock_reference_checks' in document:
        try:
            at=datetime.fromisoformat(document['stock_reference_checks']['payload']['retrieved_at'])
            refresh_stocks = force or not 0 <= (clock()-at).total_seconds() <= 15
        except (ValueError, KeyError, TypeError):
            refresh_stocks = True
        if refresh_stocks:
            symbols=[r['requested_symbol'] for r in document.get('captures',[]) if r['market']=='stocks']
            if symbols:
                # Read-only market credentials only. Catalogue reuse retains its
                # original clock and expires at ten minutes; no sliding refresh.
                market_env={k:env[k] for k in ('ALPACA_API_KEY','ALPACA_API_SECRET') if k in env}
                replace('stock_reference_checks',collect(symbols,env=market_env,clock=clock,
                    catalogue_record=document['stock_reference_checks']))
    return current, {'checked_at':clock().isoformat(),'refreshed_fields':changed,
        'retained_history_and_news_timestamps':True,'model_calls':0,'trade_authorized':False}
