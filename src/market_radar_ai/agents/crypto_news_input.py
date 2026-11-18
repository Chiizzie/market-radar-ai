"""Explicit provider-symbol mapping for optional crypto news; no guessed relevance."""
from copy import deepcopy
from hashlib import sha256
from typing import Literal
from pydantic import AwareDatetime, model_validator
from .paper_team import Frozen
from .combined_input import MarketEvidence
from .crypto_input import build_crypto_input, GAPS
from .news_input import NewsResearchInput, build_news_input
from ..evidence.news import EvidenceItem

PROVIDER_SYMBOLS={'XBTEUR':'CRYPTO:BTC','ETHEUR':'CRYPTO:ETH','SOLEUR':'CRYPTO:SOL'}
NEWS_GAPS=(*GAPS[1:], 'crypto_news_coverage_incomplete')


class CryptoNewsResearchInput(Frozen):
    schema_version: Literal['crypto-research-v2']='crypto-research-v2'
    asset_class: Literal['crypto']='crypto'
    symbol: Literal['XBTEUR','ETHEUR','SOLEUR']
    assembled_at: AwareDatetime
    market: MarketEvidence
    news: NewsResearchInput
    news_status: Literal['partial']='partial'
    news_provider: Literal['alpha_vantage']='alpha_vantage'
    broker_eligibility: Literal['UNKNOWN']='UNKNOWN'
    source_ids: tuple[str,...]
    missing_data: tuple[str,...]=NEWS_GAPS
    trade_authorized: Literal[False]=False

    @model_validator(mode='after')
    def check(self):
        if (self.market.symbol!=self.symbol or self.market.provider!='kraken'
                or self.market.quote_currency!='EUR' or self.market.validated_at!=self.assembled_at
                or self.news.symbol!=self.symbol or self.news.assembled_at!=self.assembled_at):
            raise ValueError('Crypto news packet identity mismatch')
        if any(PROVIDER_SYMBOLS[self.symbol] not in item.symbols or item.kind!='news'
               for item in self.news.evidence):
            raise ValueError('Explicit provider crypto association required')
        if self.source_ids!=(*self.news.source_ids,self.market.source_id()) or self.missing_data!=NEWS_GAPS:
            raise ValueError('Crypto citations or mandatory gaps changed')
        return self

    def digest(self):
        return sha256(self.model_dump_json().encode()).hexdigest()


def build_crypto_news_input(document, feed, *, symbol, now):
    base=build_crypto_input(document,symbol=symbol,now=now)
    if feed.get('provider')!='alpha_vantage':
        raise ValueError('Unsupported crypto news provider')
    mapped=deepcopy(feed)
    # Never infer relevance from a title, ordinary equity ticker or requested pair.
    # Preserve provider symbols alongside the explicit EUR-pair alias.
    mapped['items']=[]
    for row in feed.get('items',[]):
        if PROVIDER_SYMBOLS[symbol] not in row.get('symbols',[]):
            continue
        item=EvidenceItem.model_validate({key:row[key] for key in EvidenceItem.model_fields if key in row})
        if row.get('evidence_id')!=item.evidence_id:
            raise ValueError('Provider evidence ID mismatch')
        mapped['items'].append({**row,'symbols':list(dict.fromkeys([*item.symbols,symbol]))})
    news=build_news_input(mapped,symbol=symbol,now=now)
    return CryptoNewsResearchInput(symbol=symbol,assembled_at=now,market=base.market,news=news,
        source_ids=(*news.source_ids,base.market.source_id()))
