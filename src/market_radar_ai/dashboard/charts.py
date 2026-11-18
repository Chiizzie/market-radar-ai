"""Bounded chart-only candles from verified captures; no invented trade levels."""
from ..market_data.limits import STOCK_RESEARCH_LIMIT, CRYPTO_RESEARCH_LIMIT
from datetime import datetime
from ..market_data.admission import FxQuote
from ..market_data.reference_quotes import digest


def build_charts(document, markets, *, now):
    fx=None
    try:
        record=document['stock_reference_checks']
        if digest(record['payload'])!=record['payload_sha256']:raise ValueError('checksum')
        quote=FxQuote.model_validate(record['payload']['fx'])
        if quote.native_currency!='USD' or not 0 <= (now-quote.observed_at).total_seconds()<900:raise ValueError('fx_age')
        fx={'eur_per_unit':str(quote.eur_per_unit),'observed_at':quote.observed_at.isoformat(),'source':quote.source}
    except (KeyError,ValueError,TypeError):pass
    output=[]
    for capture in document['captures']:
        row=next(r for r in markets[capture['market']] if r['symbol']==capture['requested_symbol'])
        if row['status']!='CURRENT_RESEARCH_DATA' or len(row['quote_currencies'])!=1:continue
        raw=capture['payload']['candles']
        # build_snapshot has already verified hashes, identity, completion and quality.
        candles=sorted(raw,key=lambda c:datetime.fromisoformat(c['timestamp'].replace('Z','+00:00')))[-60:]
        if len(candles)<2:continue
        currency=row['quote_currencies'][0]
        output.append({'market':capture['market'],'symbol':row['symbol'],'provider':row['provider'],
                       'quote_currency':currency,'retrieved_at':row['retrieved_at'],
                       'capture_sha256':capture['payload_sha256'],
                       'fx':fx if currency=='USD' else None,
                       'candles':[{k:c[k] for k in ('timestamp','open','high','low','close','volume')} for c in candles]})
    if len(output)>STOCK_RESEARCH_LIMIT+CRYPTO_RESEARCH_LIMIT:raise ValueError('chart_series_limit')
    return {'schema_version':'capture-charts-v1','series':output}
