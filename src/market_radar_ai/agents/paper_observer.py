"""Read-only, fresh reference quotes for already-approved paper simulations."""
from ..market_data.limits import STOCK_RESEARCH_LIMIT
from datetime import datetime, timezone
from .paper_outcomes import Quote
from ..market_data.stock_checks import get, QUOTES, CLOCK, assess
from ..market_data.providers.fx import YahooFxProvider
from ..market_data.reference_quotes import capture_quotes, validate_capture, digest
import requests


class ReferenceObserver:
    def __init__(self, env, *, clock=lambda: datetime.now(timezone.utc), session=None,
                 fx_provider=None, crypto_fetch=capture_quotes):
        self.env=env; self.clock=clock; self.session=session or requests.Session()
        self.fx_provider=fx_provider or YahooFxProvider()
        self.crypto_fetch=crypto_fetch; self.fx=None; self.fx_fetched_at=None

    def fetch(self, decisions):
        stocks=[d for d in decisions if d['candidate_id'].startswith('stocks:')]
        crypto=[d for d in decisions if d['candidate_id'].startswith('crypto:')]
        if len(decisions)!=len(stocks)+len(crypto): raise ValueError('unsupported_paper_market')
        if any(d['plan']['currency']!='EUR' or d['plan']['native_currency']!=('USD' if d in stocks else 'EUR') for d in decisions):
            raise ValueError('paper_observer_currency_mismatch')
        quotes={}; failures=[]
        if stocks:
            stage='validation'
            try:
                symbols=list(dict.fromkeys(d['plan']['symbol'] for d in stocks))
                if len(symbols)>STOCK_RESEARCH_LIMIT: raise ValueError('paper_stock_capacity')
                now=self.clock()
                if (self.fx is None or self.fx_fetched_at is None
                    or not 0 <= (now-self.fx_fetched_at).total_seconds() < 300
                    or not 0 <= (now-self.fx.observed_at).total_seconds() <= 900):
                    stage='fx'
                    self.fx=self.fx_provider.fetch('USD',now=now)
                    self.fx_fetched_at=self.clock()
                payload={'schema_version':'stock-reference-checks-v1','symbols':symbols,
                         'catalogue_candidates':{},'trade_authorized':False,
                         'fx':self.fx.model_dump(mode='json')}
                stage='clock'
                payload['market_clock']=get(CLOCK,{},self.env,self.session)
                stage='quotes'
                payload['quotes']=get(QUOTES,{'symbols':','.join(symbols),'feed':'iex','currency':'USD'},self.env,self.session)
                payload['retrieved_at']=self.clock().isoformat()
                stage='validation'
                checked=assess(payload,now=self.clock())
                if checked['market_clock']['status']!='open' or checked['fx_status']!='current_indicative':
                    raise ValueError('stock_reference_session_or_fx')
                for row in checked['stocks']:
                    if row['quote_status']!='current_reference_only':
                        failures.append('stock_quote_unavailable:'+row['symbol']); continue
                    q=Quote(observed_at=row['observed_at'],bid=row['indicative_bid_eur'],ask=row['indicative_ask_eur'])
                    source='alpaca_iex:'+digest({'symbol':row['symbol'],'quote':payload['quotes']['quotes'][row['symbol']],
                                               'fx':str(self.fx.eur_per_unit)})
                    quotes['stocks:'+row['symbol']]=(q,source)
            except (requests.RequestException,RuntimeError,ValueError,KeyError,TypeError,ArithmeticError):
                failures.append('stock_'+stage+'_unavailable')
        if crypto:
            try:
                pairs=list(dict.fromkeys(d['plan']['symbol'] for d in crypto))
                captured=self.crypto_fetch(pairs,session=self.session,clock=self.clock)
                for symbol,row in validate_capture(captured,now=self.clock()).items():
                    quotes['crypto:'+symbol]=(Quote(observed_at=row['retrieved_at'],bid=row['bid'],ask=row['ask']),
                                               'kraken:'+row['source_payload_sha256'])
            except (requests.RequestException,ValueError,KeyError,TypeError,ArithmeticError):
                failures.append('crypto_reference_observation_unavailable')
        observations=[]
        for d in decisions:
            found=quotes.get(d['candidate_id'])
            if found is None: continue
            q,source=found
            if not datetime.fromisoformat(d['evaluated_at']) <= q.observed_at <= datetime.fromisoformat(d['plan']['exit_by']):
                continue
            observations.append({'packet_id':d['packet_id'],'symbol':d['plan']['symbol'],
                                 'quote':q.model_dump(mode='json'),'source':source})
        return observations,failures


def main():
    """Provider smoke check only; never registers a plan or sends notifications."""
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify-crypto',action='store_true',required=True)
    args=p.parse_args()
    now=lambda:datetime.now(timezone.utc)
    captured=capture_quotes(['XBTEUR'],clock=now)
    try:
        quotes=validate_capture(captured,now=now())
        result={'state':'current_crypto_reference_verified','verified_pairs':list(quotes),
                'observed_at':captured['retrieved_at'],'timestamp_basis':'LOCAL_RECEIPT_ONLY'}
    except (ValueError,KeyError,TypeError):
        result={'state':'crypto_reference_unavailable'}
    result.update(model_calls=0,plans_created=0,trade_authorized=False)
    print(json.dumps(result))
    return int(result['state']!='current_crypto_reference_verified')


if __name__=='__main__': raise SystemExit(main())
