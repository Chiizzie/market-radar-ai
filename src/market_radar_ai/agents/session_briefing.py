"""Universe-wide preparation from prior-session/news evidence, without a bar gate."""
from datetime import datetime
from zoneinfo import ZoneInfo
from .context_packages import build_context_packages
from .candidate_packages import digest

SCHEMA = 'session-evidence-package-v1'


def briefing_slot(now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    dublin=now.astimezone(ZoneInfo('Europe/Dublin'))
    ny=now.astimezone(ZoneInfo('America/New_York'))
    if dublin.weekday()>=5 or not 8<=dublin.hour<22:
        return None
    minutes=ny.hour*60+ny.minute
    if minutes<510: return 'morning'
    if minutes<570: return 'preopen'
    if minutes<600: return 'opening'
    if minutes<960: return 'intraday'
    return None


def build_briefing(document, feed, *, now):
    """Reproduce validated context into bounded exact facts for every covered stock."""
    slot=briefing_slot(now)
    if slot is None: return {'packages':[]}
    batch=build_context_packages(document,feed,now=now)
    requested=sorted({r['requested_symbol'] for r in document['captures'] if r['market']=='stocks'})
    if len(requested)>20: raise ValueError('briefing_universe_limit')
    from ..market_data.stock_checks import briefing_references
    references=briefing_references(document,now=now)
    covered=[]; sources={}; by_symbol={}; news_ids=[]; calendar_ids=[]; macro_ids=[]; expiries=[]
    for record in sorted(batch['packages'],key=lambda r:r['package']['symbol']):
        p=record['package']; symbol=p['symbol'];covered.append(symbol)
        expiries.append(datetime.fromisoformat(p['expires_at']))
        original=next(s for sid,s in p['sources'].items() if sid.startswith('context:'))
        daily=original['daily']['bars']; intraday=original['intraday']['bars']
        summary=dict(schema_version='stock-session-summary-v1',symbol=symbol,native_currency='USD',
            provider='alpaca_iex',retrieved_at=original['retrieved_at'],
            original_context_sha256=original['original_context_sha256'],
            prior_session=daily[-1] if daily else None,
            latest_completed_intraday=intraday[-1] if intraday else None,
            daily_bar_count=len(daily),intraday_bar_count=len(intraday),
            daily_status=original['daily']['status'],intraday_status=original['intraday']['status'],
            research_mode=p['research_mode'],use='CONTEXT_ONLY_NOT_EXECUTABLE',
            phase_is_exchange_calendar_verified=False,trade_authorized=False)
        if symbol in references:
            summary['reference_checks']=references[symbol]
        sid='context:'+digest(summary);sources[sid]=summary
        symbol_sources=[sid]
        # One latest linked story per stock, one shared macro source, retained calendars.
        for source_id in p['news_source_ids'][:1]+p.get('calendar_source_ids',[]):
            sources[source_id]=p['sources'][source_id];symbol_sources.append(source_id)
            (news_ids if source_id.startswith('news:') else calendar_ids).append(source_id)
        if not macro_ids and p['macro_source_ids']:
            source_id=p['macro_source_ids'][0];sources[source_id]=p['sources'][source_id];macro_ids.append(source_id)
        by_symbol[symbol]={'source_ids':symbol_sources,'missing_evidence':p['missing_evidence']}
    if not covered: return {'packages':[]}
    gaps=['broker_account_eligibility_unverified','executable_quotes_and_costs_missing',
          'eur_trade_plan_missing','fresh_fx_conversion_missing','independent_catalyst_confirmation_missing',
          'exchange_session_not_verified','iex_limited_market_coverage','six_agent_review_not_run',
          'context_is_not_trade_admission','corporate_actions_not_verified','complete_event_calendar_missing']
    converted=all(references.get(s,{}).get('indicative_bid_eur') is not None for s in covered)
    if converted:gaps.remove('fresh_fx_conversion_missing')
    body=dict(schema_version=SCHEMA,candidate_id='stocks:MARKET_OVERVIEW',symbol='MARKET_OVERVIEW',
        market='stocks',research_mode=slot.upper()+'_BRIEFING',review_slot=slot,
        assembled_at=now.isoformat(),expires_at=min(expiries).isoformat(),
        native_currency='USD',reporting_currency='EUR',eur_conversion='indicative_reference_only' if converted else 'not_supplied',
        requested_symbols=requested,covered_symbols=covered,
        unavailable_symbols=[s for s in requested if s not in covered],
        sources=sources,source_ids=list(sources),symbol_evidence=by_symbol,
        news_source_ids=list(dict.fromkeys(news_ids)),macro_source_ids=macro_ids,
        calendar_source_ids=list(dict.fromkeys(calendar_ids)),
        context_only_news_ids=[sid for sid in set(news_ids+macro_ids) if not sources[sid]['intraday_recent']],
        missing_evidence=gaps,roles=p['roles'],constraints=p['constraints'],
        research_questions=['Prioritise or avoid each covered stock for the opening watchlist.',
            'State what changed, cited catalysts, bullish/bearish opening conditions and invalidation.',
            'Do not invent missing news, forecasts, live prices, converted EUR levels or trade approval.',
            'reference_checks are frozen observations: obey quote_expires_at, never call them executable or current after expiry. Indicative EUR quotes are not a EUR trade plan.'],
        usage_note='Whole requested stock universe preparation. Prior-session levels are historical USD context. No twenty-bar requirement; missing current-session candles do not prevent research. Watchlist decisions are not trade calls.',
        review_status='NOT_RUN',model_calls=0,trade_authorized=False,plan=None)
    # Deterministic source/field ordering across processes.
    body['context_only_news_ids'].sort()
    return {'packages':[{'package_id':digest(body),'package':body}]}
