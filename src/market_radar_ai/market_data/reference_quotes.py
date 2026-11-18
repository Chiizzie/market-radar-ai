"""Kraken public EUR bid/ask research references, never another broker's quote."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import requests

from .crypto_identities import PAIRS, IDENTITIES
from .limits import REFERENCE_PAIR_LIMIT
BASE = 'https://api.kraken.com/0/public/'


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def get_json(path, params, session):
    with session.get(BASE+path, params=params, timeout=(5,10), allow_redirects=False, stream=True) as response:
        if response.status_code!=200:raise ValueError('reference_http_failure')
        body=bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body)>1_000_000:raise ValueError('reference_body_too_large')
    return json.loads(body)


def capture_quotes(pairs, *, session=None, clock=lambda:datetime.now(timezone.utc)):
    pairs=list(dict.fromkeys(pairs))
    if not pairs or any(p not in PAIRS for p in pairs):raise ValueError('unsupported_reference_pair')
    started=clock()
    if started.tzinfo is None:raise ValueError('aware_clock_required')
    result={'schema_version':'kraken-reference-capture-v1','requested_pairs':pairs,
            'request_started_at':started.isoformat(),'status':'error','trade_authorized':False}
    try:
        params={'pair':','.join(pairs)}
        transport=session or requests.Session()
        payload={'asset_pairs':get_json('AssetPairs',params,transport),
                 'tickers':get_json('Ticker',params,transport)}
        result.update(status='ok',retrieved_at=clock().isoformat(),payload=payload,payload_sha256=digest(payload))
        # Reject malformed API envelopes immediately; no stale fallback or retry.
        valid=validate_capture(result,now=clock())
        result['unavailable_pairs']=[p for p in pairs if p not in valid]
        if result['unavailable_pairs']:result['status']='partial'
    except (requests.RequestException, ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
        result={'schema_version':'kraken-reference-capture-v1','requested_pairs':pairs,
                'request_started_at':started.isoformat(),'retrieved_at':clock().isoformat(),
                'status':'error','reason':'reference_quotes_unavailable','trade_authorized':False}
    return result


def validate_capture(capture, *, now):
    if now.tzinfo is None:raise ValueError('aware_clock_required')
    if (capture['schema_version']!='kraken-reference-capture-v1' or capture['status'] not in ('ok','partial')
            or capture['trade_authorized'] is not False):raise ValueError('invalid_reference_capture')
    started=datetime.fromisoformat(capture['request_started_at'])
    received=datetime.fromisoformat(capture['retrieved_at'])
    if started.tzinfo is None or received.tzinfo is None:
        raise ValueError('aware_reference_timestamps_required')
    if not 0 <= (received-started).total_seconds() <= 20 or not 0 <= (now-received).total_seconds() < 30:
        raise ValueError('stale_or_slow_reference_capture')
    payload=capture['payload']
    if digest(payload)!=capture['payload_sha256']:raise ValueError('reference_checksum_mismatch')
    meta,tickers=payload['asset_pairs'],payload['tickers']
    if meta['error'] or tickers['error']:raise ValueError('reference_provider_error')
    pairs=capture['requested_pairs']
    if not isinstance(pairs,list) or not 1<=len(pairs)<=REFERENCE_PAIR_LIMIT or len(set(pairs))!=len(pairs):
        raise ValueError('invalid_reference_pairs')
    if any(pair not in PAIRS for pair in pairs):raise ValueError('unsupported_reference_pair')
    quotes={}
    for pair in pairs:
        try:
            candidates=[(key,row) for key,row in meta['result'].items() if row.get('altname')==pair]
            if len(candidates)!=1:raise ValueError('reference_identity_ambiguous')
            key,row=candidates[0]
            if key!=IDENTITIES[pair][4]:raise ValueError('reference_internal_identity_invalid')
            if (row['base']!=PAIRS[pair][0] or row['quote']!='ZEUR'
                    or row['wsname']!=PAIRS[pair][1] or row['status']!='online'):
                raise ValueError('reference_identity_or_status_invalid')
            ticker=tickers['result'][key]
            if any(not isinstance(ticker.get(side),list) or len(ticker[side])!=3 for side in ('a','b')):
                raise ValueError('invalid_reference_ticker_shape')
            if any(not isinstance(v,str) for v in (ticker['b'][0],ticker['a'][0],ticker['b'][2],ticker['a'][2])):
                raise ValueError('decimal_strings_required')
            bid,ask=Decimal(ticker['b'][0]),Decimal(ticker['a'][0])
            bid_size,ask_size=Decimal(ticker['b'][2]),Decimal(ticker['a'][2])
            if not all(v.is_finite() and v>0 for v in (bid,ask,bid_size,ask_size)) or bid>ask:
                raise ValueError('invalid_reference_prices')
            quotes[pair]={'schema_version':'reference-quote-v1','symbol':pair,'venue':'kraken',
                'quote_currency':'EUR','bid':str(bid),'ask':str(ask),
                'bid_size':str(bid_size),'ask_size':str(ask_size),
                'spread_bps':str((ask-bid)/((ask+bid)/2)*10000),
                'retrieved_at':received.isoformat(),'exchange_timestamp':None,
                'expires_at':(received+timedelta(seconds=30)).isoformat(),
                'timestamp_basis':'LOCAL_RECEIPT_ONLY','broker_executable':False,
                'source_payload_sha256':capture['payload_sha256'],
                'limitations':['Public venue quote, not a Robinhood executable quote',
                               'No account eligibility, personal fee tier or slippage verification']}
        except (ValueError,KeyError,TypeError,ArithmeticError,AttributeError,IndexError):
            # Fail this asset closed; another valid identity keeps its own quote.
            continue
    if not quotes:raise ValueError('no_valid_reference_quotes')
    return quotes


def enrich(document, *, capture_fetch=capture_quotes, clock=lambda:datetime.now(timezone.utc)):
    result=deepcopy(document)
    pairs=[c['requested_symbol'] for c in document['captures'] if c['market']=='crypto' and c['requested_symbol'] in PAIRS]
    if pairs:result['reference_quote_capture']=capture_fetch(pairs,clock=clock)
    return result


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.capture.stat().st_size>4_000_000:raise ValueError('input_too_large')
    result=enrich(json.loads(args.capture.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    ref=result.get('reference_quote_capture',{})
    print(json.dumps({'reference_quotes':ref.get('status','not_requested'),'trade_authorized':False}))


if __name__=='__main__':main()
