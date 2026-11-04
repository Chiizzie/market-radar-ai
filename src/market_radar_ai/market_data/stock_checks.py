"""Read-only stock reference checks. Never supplies broker execution permission."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import requests
from .providers.alpaca import SYMBOL
from .providers.catalogues import Trading212Catalogue
from .providers.fx import YahooFxProvider
from .admission import FxQuote
from .reference_quotes import digest

QUOTES='https://data.alpaca.markets/v2/stocks/quotes/latest'
CLOCK='https://paper-api.alpaca.markets/v2/clock'


def timestamp(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.tzinfo is None: raise ValueError('aware_timestamp_required')
    return at


def get(url, params, env, session):
    key,secret=env.get('ALPACA_API_KEY'),env.get('ALPACA_API_SECRET')
    if not key or not secret: raise ValueError('credentials_missing')
    with session.get(url,params=params,headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},
                     timeout=(5,10),allow_redirects=False,stream=True) as response:
        if response.status_code!=200: raise ValueError('provider_unavailable')
        body=bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body)>500000: raise ValueError('response_too_large')
    return json.loads(body)


def assess(payload, *, now):
    if now.tzinfo is None: raise ValueError('aware_clock_required')
    if (payload['schema_version']!='stock-reference-checks-v1' or payload['trade_authorized'] is not False
            or not 0 <= (now-timestamp(payload['retrieved_at'])).total_seconds() <= 60):
        raise ValueError('invalid_or_stale_checks')
    symbols=payload['symbols']
    if not isinstance(symbols,list) or not 1<=len(symbols)<=20 or len(set(symbols))!=len(symbols) or any(not isinstance(s,str) or not SYMBOL.fullmatch(s) for s in symbols):
        raise ValueError('invalid_symbols')
    clock={'status':'unavailable','instrument_halts_verified':False}
    try:
        c=payload['market_clock']
        if type(c['is_open']) is not bool or not 0 <= (now-timestamp(c['timestamp'])).total_seconds() <=60:
            raise ValueError('clock_stale')
        if min(timestamp(c['next_open']),timestamp(c['next_close']))<=timestamp(c['timestamp']):
            raise ValueError('clock_order')
        clock={'status':'open' if c['is_open'] else 'closed','source':'alpaca_us_market_clock',
               'observed_at':c['timestamp'],'next_close':c['next_close'],'instrument_halts_verified':False}
    except (KeyError,TypeError,ValueError,AttributeError): pass
    fx=None
    try:
        q=FxQuote.model_validate(payload['fx'])
        if q.native_currency!='USD' or not 0 <= (now-q.observed_at).total_seconds()<=900: raise ValueError('fx_stale')
        fx=q
    except (KeyError,TypeError,ValueError): pass
    rows=[]
    for symbol in symbols:
        row={'symbol':symbol,'quote_status':'unavailable','broker_executable':False,
             'eligibility_verified':False,'catalogue_status':'unavailable','trade_authorized':False}
        try:
            candidates=payload['catalogue_candidates'][symbol]
            if not isinstance(candidates,list):raise ValueError('candidate_shape')
            row['catalogue_status']='single_candidate_unverified' if len(candidates)==1 else 'ambiguous' if candidates else 'not_found'
            row['catalogue_candidates']=candidates
        except (KeyError,TypeError,ValueError): pass
        try:
            envelope=payload['quotes']
            if envelope.get('currency','USD')!='USD':raise ValueError('currency')
            q=envelope['quotes'][symbol]
            at=timestamp(q['t'])
            if not 0 <= (now-at).total_seconds()<=30:raise ValueError('quote_stale')
            bid,ask,bs,asz=[Decimal(str(q[k])) for k in ('bp','ap','bs','as')]
            if not all(v.is_finite() and v>0 for v in (bid,ask,bs,asz)) or bid>ask:raise ValueError('quote_invalid')
            row.update(quote_status='current_reference_only',feed='iex',native_currency='USD',
                       bid=str(bid),ask=str(ask),observed_at=q['t'],spread_bps=str((ask-bid)/((ask+bid)/2)*10000))
            if fx:
                row.update(indicative_bid_eur=str(bid*fx.eur_per_unit),indicative_ask_eur=str(ask*fx.eur_per_unit),
                           fx_observed_at=fx.observed_at.isoformat(),fx_source=fx.source)
        except (KeyError,TypeError,ValueError,ArithmeticError,AttributeError): pass
        row['remaining_blockers']=['broker_account_permission_unverified','broker_executable_quote_missing',
            'broker_fees_and_slippage_missing','instrument_halt_status_unknown','eur_trade_plan_missing']
        if row['quote_status']!='current_reference_only':row['remaining_blockers'].append('stock_reference_quote_unavailable_or_stale')
        if fx is None:row['remaining_blockers'].append('fx_unavailable_or_stale')
        if clock['status']!='open':row['remaining_blockers'].append('regular_session_not_confirmed_open')
        rows.append(row)
    return {'schema_version':'stock-check-readiness-v1','evaluated_at':now.isoformat(),'market_clock':clock,
            'fx_status':'current_indicative' if fx else 'unavailable_or_stale','stocks':rows,'trade_authorized':False}


def collect(symbols, *, env, clock=lambda:datetime.now(timezone.utc), session=None, catalogue=None, fx_provider=None):
    symbols=list(dict.fromkeys(symbols))
    if not 1<=len(symbols)<=20 or any(not isinstance(s,str) or not SYMBOL.fullmatch(s) for s in symbols):raise ValueError('invalid_symbols')
    payload={'schema_version':'stock-reference-checks-v1','symbols':symbols,'trade_authorized':False,
             'catalogue_candidates':{},'failures':[]}
    # Slow metadata/FX first; short-lived quotes and clock collected last.
    try:
        rows=(catalogue or Trading212Catalogue()).fetch()
        for symbol in symbols:
            matches=[r for r in rows if r.ticker==symbol+'_US_EQ' and r.currencyCode=='USD' and r.type in ('STOCK','ETF')]
            payload['catalogue_candidates'][symbol]=[{'ticker':r.ticker,'isin':r.isin,'name':r.name,'currency':r.currencyCode,'type':r.type} for r in matches]
    except Exception:payload['failures'].append('catalogue_unavailable')
    try:payload['fx']=(fx_provider or YahooFxProvider()).fetch('USD',now=clock()).model_dump(mode='json')
    except Exception:payload['failures'].append('fx_unavailable')
    transport=session or requests.Session()
    for name,url,params in [('market_clock',CLOCK,{}),('quotes',QUOTES,{'symbols':','.join(symbols),'feed':'iex','currency':'USD'})]:
        try:payload[name]=get(url,params,env,transport)
        except Exception:payload['failures'].append(name+'_unavailable')
    payload['retrieved_at']=clock().isoformat()
    return {'payload':payload,'payload_sha256':digest(payload)}


def evaluate(record, *, now):
    if digest(record['payload'])!=record['payload_sha256']:raise ValueError('checks_checksum')
    return assess(record['payload'],now=now)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    doc=json.loads(args.capture.read_text())
    symbols=[r['requested_symbol'] for r in doc['captures'] if r['market']=='stocks']
    doc['stock_reference_checks']=collect(symbols,env=os.environ)
    args.output.write_text(json.dumps(doc,indent=2)+'\n')

if __name__=='__main__': main()
