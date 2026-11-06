"""Public EU catalogue plus independent EUR venue references for paper use only."""
from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .providers.robinhood import RobinhoodEuropeCatalogue
from .reference_quotes import digest, validate_capture

SCOPE = 'public_europe_support_list_not_account_verification'
from .crypto_identities import ASSETS


def catalogue(record, *, now):
    p = record['payload']
    if (record['payload_sha256'] != digest(p) or p['source'] != RobinhoodEuropeCatalogue.URL
            or p['scope'] != SCOPE):
        raise ValueError('invalid_crypto_catalogue')
    at = datetime.fromisoformat(p['retrieved_at'])
    if at.tzinfo is None or not 0 <= (now-at).total_seconds() < 86400:
        raise ValueError('stale_crypto_catalogue')
    assets = p['assets']
    if (not isinstance(assets, list) or not 1 <= len(assets) <= 500
            or any(set(a) != {'symbol','name'} or not isinstance(a['symbol'],str)
                   or not isinstance(a['name'],str) for a in assets)
            or len({a['symbol'] for a in assets}) != len(assets)):
        raise ValueError('ambiguous_crypto_catalogue')
    return deepcopy(p)


def enrich(document, *, fetch=None, clock=lambda:datetime.now(timezone.utc)):
    result = deepcopy(document)
    try:
        payload = (fetch or RobinhoodEuropeCatalogue().fetch)()
        record = {'payload':payload, 'payload_sha256':digest(payload)}
        catalogue(record, now=clock())
        result['crypto_catalogue'] = record
    except Exception:
        # No stale fallback and no exception strings/provider bodies in logs.
        result['crypto_catalogue'] = {'status':'unavailable', 'trade_authorized':False}
    return result


def assess(document, *, symbol, now):
    result = {}
    try:
        p = catalogue(document['crypto_catalogue'], now=now)
        identity = ASSETS[symbol]
        matches = [a for a in p['assets'] if a['symbol'] == identity[0]]
        result['catalogue_candidate'] = 'PASS' if matches == [{'symbol':identity[0], 'name':identity[1]}] else 'FAIL'
        result['catalogue_scope'] = SCOPE
        result['catalogue_source'] = p['source']
    except (ValueError,KeyError,TypeError):
        pass
    try:
        q = validate_capture(document['reference_quote_capture'], now=now)[symbol]
        result.update(reference_quote='PASS', indicative_ask_eur=q['ask'],
                      quote_observed_at=q['retrieved_at'], reference_expires_at=q['expires_at'], fx='PASS',
                      reference_venue='kraken', fx_basis='native_EUR_no_conversion')
        local = now.astimezone(ZoneInfo('Europe/Dublin'))
        allowed = local.weekday()<5 and 8<=local.hour<22
        result['market_session'] = 'PASS' if allowed else 'FAIL'
        result['session_basis'] = 'online_reference_venue_and_weekday_Dublin_window'
        if allowed:result['exit_deadline'] = local.replace(hour=22,minute=0,second=0,microsecond=0).isoformat()
    except (ValueError,KeyError,TypeError,ArithmeticError):
        pass
    return result


def main():
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.capture.stat().st_size>4_000_000:raise ValueError('input_too_large')
    result=enrich(json.loads(args.capture.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'crypto_catalogue':'current_public_list' if 'payload' in result['crypto_catalogue'] else 'unavailable',
                      'account_permission_verified':False,'model_calls':0,'trade_authorized':False}))


if __name__=='__main__':main()
