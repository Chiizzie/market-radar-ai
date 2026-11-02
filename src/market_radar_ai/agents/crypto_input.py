"""Explicit candle-only crypto research; no fabricated news or broker approval."""
from hashlib import sha256
from typing import Literal
from pydantic import AwareDatetime, model_validator
from .paper_team import Frozen
from .combined_input import MarketEvidence, build_market_evidence

PAIRS=('XBTEUR','ETHEUR','SOLEUR')
GAPS=('crypto_news_not_supplied','robinhood_account_eligibility_unverified',
      'eur_risk_and_trade_plan_not_supplied','catalyst_significance_unverified')


class CryptoResearchInput(Frozen):
    schema_version: Literal['crypto-research-v1']='crypto-research-v1'
    asset_class: Literal['crypto']='crypto'
    symbol: Literal['XBTEUR','ETHEUR','SOLEUR']
    assembled_at: AwareDatetime
    market: MarketEvidence
    news: None = None
    news_status: Literal['not_connected']='not_connected'
    broker_eligibility: Literal['UNKNOWN']='UNKNOWN'
    source_ids: tuple[str,...]
    missing_data: tuple[str,...]=GAPS
    trade_authorized: Literal[False]=False

    @model_validator(mode='after')
    def check(self):
        if (self.market.symbol!=self.symbol or self.market.provider!='kraken'
                or self.market.quote_currency!='EUR' or self.market.validated_at!=self.assembled_at):
            raise ValueError('Crypto market identity mismatch')
        if self.source_ids!=(self.market.source_id(),) or self.missing_data!=GAPS:
            raise ValueError('Crypto citations or mandatory gaps changed')
        return self

    def digest(self):
        return sha256(self.model_dump_json().encode()).hexdigest()


def build_crypto_input(document, *, symbol, now):
    if symbol not in PAIRS:raise ValueError('Unsupported research pair')
    market=build_market_evidence(document,symbol=symbol,now=now,market_name='crypto')
    return CryptoResearchInput(symbol=symbol,assembled_at=now,market=market,
                               source_ids=(market.source_id(),))
